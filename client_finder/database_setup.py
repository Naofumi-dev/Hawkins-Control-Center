"""Back up the owned database and optionally install inbox migrations 004 and 005."""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path

from .configuration import CONFIG_KEYS, ConfigurationError, default_config_path, verify_connection
from .gmail import OWNER_EMAIL


# Verified in the personal project's Connect dialog. Never accept a caller-supplied host.
PG_HOST = "aws-0-ap-northeast-2.pooler.supabase.com"
PG_USER = "postgres.mtdavgadkiiofwikzdtn"
ROOT = Path(__file__).resolve().parents[1]
CA_FILE = ROOT / "data" / "supabase-ca.crt"
CA_SHA256 = "700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7"
MIGRATIONS = ("004_personal_inbox.sql", "005_conversation_replies.sql")
ACQUISITION_MIGRATIONS = ("006_acquisition_workspace.sql", "007_job_applications.sql", "008_acquisition_controls.sql")
HISTORY_SQL = """select jsonb_build_object(
 'leads',(select count(*) from public.cold_leads),
 'campaigns',(select count(*) from public.cold_campaigns),
 'suppressions',(select count(*) from public.client_finder_suppressions),
 'send_attempts',(select count(*) from public.client_finder_send_attempts))"""


class DatabaseSetupError(ConfigurationError):
    pass


def client_tools() -> dict[str, str]:
    for prefix in ("/opt/homebrew/opt/libpq@17/bin", "/usr/local/opt/libpq@17/bin"):
        tools = {name: str(Path(prefix) / name) for name in ("psql", "pg_dump", "pg_restore")}
        if all(Path(path).is_file() for path in tools.values()):
            return tools
    raise DatabaseSetupError("Install the official PostgreSQL 17 client tools: brew install libpq@17")


def run_client(command: list[str], environment: dict, *, sql: str | None = None, stage: str) -> str:
    try:
        result = subprocess.run(command, input=sql, text=True, capture_output=True,
                                env=environment, timeout=600, check=False)
    except subprocess.TimeoutExpired:
        raise DatabaseSetupError(stage + " timed out. Check the database state before retrying.") from None
    if result.returncode:
        reason = "database_operation_unconfirmed"
        for diagnostic, code in (("password authentication failed", "database_password_rejected"),
                                 ("certificate verify failed", "tls_verification_failed"),
                                 ("permission denied", "database_permission_denied"),
                                 ("could not translate host", "database_host_unavailable")):
            if diagnostic in result.stderr.lower():
                reason = code
                break
        # Provider errors may include private values; never print raw output or credentials.
        raise DatabaseSetupError(f"{stage} failed ({reason}). No retry was performed.")
    return result.stdout


def pg_environment(password_file: Path) -> dict[str, str]:
    if not CA_FILE.is_file() or hashlib.sha256(CA_FILE.read_bytes()).hexdigest() != CA_SHA256:
        raise DatabaseSetupError("The verified Supabase root certificate is missing or changed")
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(("PG", "SUPABASE_", "CLIENT_FINDER_", "GOOGLE_", "GMAIL_", "OPENROUTER_"))}
    environment.update(PGHOST=PG_HOST, PGPORT="5432", PGDATABASE="postgres", PGUSER=PG_USER,
                       PGPASSFILE=str(password_file), PGSSLMODE="verify-full", PGSSLROOTCERT=str(CA_FILE),
                       PGCONNECT_TIMEOUT="20", PGAPPNAME="hawkins-personal-database-setup")
    return environment


def write_password_file(path: Path, password: str) -> None:
    if not password or any(ch in password for ch in "\r\n\x00"):
        raise DatabaseSetupError("Enter the database password as one nonempty line")
    escaped = password.replace("\\", "\\\\").replace(":", "\\:")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(f"{PG_HOST}:5432:postgres:{PG_USER}:{escaped}\n")


def migration_body(sql: str) -> str:
    # Only remove the known outer transaction wrappers, never a function's BEGIN.
    statements = re.findall(r"(?m)^(?:begin|commit);\s*$", sql)
    if [part.strip() for part in statements] != ["begin;", "commit;"]:
        raise DatabaseSetupError("Migration transaction wrappers changed; review before applying")
    return re.sub(r"(?m)^(?:begin|commit);\s*$", "", sql)


def migration_bundle(history: dict) -> str:
    if set(history) != {"leads", "campaigns", "suppressions", "send_attempts"} or any(type(v) is not int or v < 0 for v in history.values()):
        raise DatabaseSetupError("Pre-migration history counts are invalid")
    statements = [
        "set local lock_timeout='5s'; set local statement_timeout='120s';",
        "lock table public.cold_leads,public.cold_campaigns,public.client_finder_suppressions,public.client_finder_send_attempts in share row exclusive mode;",
        "do $guard$ begin if to_regclass('public.client_finder_mailboxes') is not null then raise exception 'inbox_already_installed'; end if; end $guard$;",
    ]
    check_history = f"""do $guard$ begin if ({HISTORY_SQL}) <> '{json.dumps(history)}'::jsonb
      then raise exception 'legacy_history_changed'; end if; end $guard$;"""
    statements.append(check_history)
    for name in MIGRATIONS:
        statements.append(migration_body((ROOT / "db" / name).read_text()))
    # These three repository queries report permission and disabled-send checks.
    checks = (ROOT / "db" / "postflight_personal.sql").read_text().split(";")[:3]
    for index, check in enumerate(checks):
        statements.append(f"""do $guard$ begin
          if not exists(select 1 from ({check}) results) or exists(select 1 from ({check}) results where result<>'PASS')
          then raise exception 'personal_postflight_{index + 1}_failed'; end if;
        end $guard$;""")
    statements.extend([check_history, "notify pgrst, 'reload schema';"])
    return "\n".join(statements)


def backup_directory() -> Path:
    parent = default_config_path().parent / "backups"
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = parent.stat()
    if parent.is_symlink() or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise DatabaseSetupError("The personal backup directory must be owned and private (mode 700)")
    directory = parent / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    return directory


def acquisition_bundle(history: dict) -> str:
    if set(history) != {"leads", "campaigns", "suppressions", "send_attempts"} or any(type(v) is not int or v<0 for v in history.values()):
        raise DatabaseSetupError("Invalid acquisition preflight counts")
    guard = f"""do $guard$ begin
      if ({HISTORY_SQL}) <> '{json.dumps(history)}'::jsonb then raise exception 'existing_history_changed'; end if;
    end $guard$;"""
    return "\n".join([
        "set local lock_timeout='5s'; set local statement_timeout='120s';",
        "lock table public.cold_leads,public.cold_campaigns,public.client_finder_suppressions,public.client_finder_send_attempts in share row exclusive mode;",
        "do $guard$ begin if to_regclass('public.client_finder_mailboxes') is null then raise exception 'inbox_foundation_required'; end if; if to_regclass('public.client_finder_jobs') is not null or to_regclass('public.client_finder_connections') is not null then raise exception 'acquisition_already_installed'; end if; end $guard$;",
        guard, *(migration_body((ROOT / "db" / n).read_text()) for n in ACQUISITION_MIGRATIONS),
        """do $guard$ declare t text; begin
          if exists(select 1 from public.client_finder_settings where sending_enabled or applications_enabled)
            or exists(select 1 from public.client_finder_mailboxes where replies_enabled) then raise exception 'sending_must_remain_disabled'; end if;
          foreach t in array array['connections','resources','jobs','workflows','workflow_runs','import_batches','history','operations','meetings','crm_links'] loop
            if has_table_privilege('anon','public.client_finder_'||t,'select') or has_table_privilege('authenticated','public.client_finder_'||t,'select')
              or has_table_privilege('service_role','public.client_finder_'||t,'insert,update,delete') then raise exception 'acquisition_permission_check_failed'; end if;
          end loop;
          if has_function_privilege('authenticated','public.client_finder_application_approve(uuid,integer,text,text,bigint,bigint,bigint)','execute') then raise exception 'application_authority_exposed'; end if;
        end $guard$;""", guard, "notify pgrst, 'reload schema';"])


def prepare_database(*, apply: bool = False, acquisition: bool = False) -> None:
    values = {name: os.environ.get(name, "") for name in CONFIG_KEYS}
    verify_connection(values)
    tools = client_tools()
    print("Personal Hawkins database only. Preparing a private schema and data backup.", flush=True)
    print("This needs the DATABASE password, separate from your Auth user password.", flush=True)
    if apply:
        print("After the backup passes, migrations " + ("006–008" if acquisition else "004 and 005") + " will run together with sending disabled.", flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        password = getpass.getpass("Personal Hawkins database password: ")
    directory = backup_directory()
    print("Private backup directory: " + str(directory), flush=True)
    old_umask = os.umask(0o077)
    try:
        with tempfile.TemporaryDirectory(prefix="credential-", dir=directory) as private:
            password_file = Path(private) / "pgpass"
            write_password_file(password_file, password)
            del password
            environment = pg_environment(password_file)
            psql = [tools["psql"], "-X", "--no-password", "--quiet", "--tuples-only", "--no-align", "--set=ON_ERROR_STOP=1"]

            def query(sql: str):
                return json.loads(run_client(psql + ["--command", sql], environment, stage="Database preflight"))

            owner_id = str(uuid.UUID(values["CLIENT_FINDER_OWNER_AUTH_ID"]))
            identity = query(f"""select json_build_object('owner_verified',exists(select 1 from auth.users
              where id='{owner_id}'::uuid and lower(email)='{OWNER_EMAIL}' and email_confirmed_at is not null),
              'version',current_setting('server_version_num')::integer,
              'outreach_disabled',(select not sending_enabled from public.client_finder_settings where id=1),
              'new_table_count',(select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='public'
              and c.relname in ('client_finder_mailboxes','client_finder_conversations','client_finder_inbox_messages',
                'client_finder_tasks','client_finder_agent_runs','client_finder_opportunities','client_finder_owner_actions')))""")
            if (identity.get("owner_verified") is not True or identity.get("outreach_disabled") is not True or
                    not 170000 <= identity.get("version", 0) < 180000):
                raise DatabaseSetupError("Database identity, PostgreSQL version, or disabled-sending check failed")
            if acquisition and identity["new_table_count"] != 7:
                raise DatabaseSetupError("Complete and verify the existing inbox foundation first")
            if acquisition:
                ready = query("select json_build_object('installed',to_regclass('public.client_finder_connections') is not null,'replies_disabled',(select not replies_enabled from public.client_finder_mailboxes where id=1))")
                if ready["installed"] or ready["replies_disabled"] is not True:
                    raise DatabaseSetupError("Acquisition already installed or replies enabled. Inspect the current state before migration")
            if apply and identity["new_table_count"] and not acquisition:
                raise DatabaseSetupError("Inbox tables already exist. Inspect postflight results instead of repeating setup")
            preflight = (ROOT / "db" / "preflight_existing.sql").read_text().split("-- OPTIONAL SECOND QUERY")[0].strip().rstrip(";")
            checks = query(f"select json_agg(results) from ({preflight}) results")
            if not checks or any(row.get("result") == "BLOCK" for row in checks):
                raise DatabaseSetupError("Existing database preflight reported a blocker; no migration was applied")
            history = query(HISTORY_SQL)
            archive = directory / ("before-acquisition.dump" if acquisition else "before-inbox.dump")
            print("Backing up the database…", flush=True)
            run_client([tools["pg_dump"], "--no-password", "--format=custom", "--file", str(archive)],
                       environment, stage="Database backup")
            listing = run_client([tools["pg_restore"], "--list", str(archive)], environment, stage="Backup inventory")
            required_tables = ("cold_leads", "cold_campaigns", "client_finder_settings", "client_finder_suppressions", "client_finder_send_attempts")
            if acquisition:
                required_tables += ("client_finder_conversations", "client_finder_inbox_messages", "client_finder_opportunities", "client_finder_tasks")
            for table in required_tables:
                if not all(f" {kind} public {table} " in listing for kind in ("TABLE", "TABLE DATA")):
                    raise DatabaseSetupError("Backup is missing required schema or data entries; no migration was applied")
            # Decode every archived payload without executing any restore against a database.
            run_client([tools["pg_restore"], "--file", os.devnull, str(archive)], environment, stage="Backup content validation")
            with archive.open("rb") as file:
                digest = hashlib.file_digest(file, "sha256").hexdigest()
            manifest = {"project": "mtdavgadkiiofwikzdtn", "created_at": datetime.now(timezone.utc).isoformat(),
                        "archive": archive.name, "bytes": archive.stat().st_size, "sha256": digest,
                        "history_counts": history, "archive_decoded": True, "restore_tested": False,
                        "migrations": {name: hashlib.sha256((ROOT / "db" / name).read_bytes()).hexdigest() for name in (ACQUISITION_MIGRATIONS if acquisition else MIGRATIONS)},
                        "migration_status": "not_applied"}
            manifest_path = directory / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            (directory / "RESTORE.md").write_text(
                "# Private Hawkins backup\n\nFull logical PostgreSQL archive; storage object files and role passwords are not included.\n"
                "The archive inventory and every payload were decoded, but a database restore was not tested.\n"
                f"Inspect with pg_restore --list {archive.name}. Test recovery in an isolated PostgreSQL 17 database with the required Supabase roles and extensions.\n"
                "Do not run a clean/overwrite restore against the live project without reviewing the target and recovery plan.\n"
                "The setup applies its complete migration bundle in one transaction; pre-commit failures roll back together.\n"
                "A lost connection at commit requires read-only postflight inspection before any retry. Use a reviewed forward migration for subsequent fixes.\n"
            )
            print(f"Backup verified: {manifest['bytes']} bytes, SHA-256 {digest}", flush=True)
            if not apply:
                print("Backup complete. No migration was requested or applied.", flush=True)
                return
            manifest["migration_status"] = "started_outcome_unconfirmed"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            print("Applying acquisition migrations and checking existing history…" if acquisition else "Applying both inbox migrations and checking permissions, limits, and existing history…", flush=True)
            run_client(psql + ["--single-transaction", "--file", "-"], environment,
                       sql=acquisition_bundle(history) if acquisition else migration_bundle(history), stage="Acquisition migration transaction" if acquisition else "Inbox migration transaction")
            manifest["migration_status"] = "committed_with_postflight_checks"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
            print("Acquisition schema ready. Existing history preserved; all sending stays disabled." if acquisition else "Inbox schema ready. Existing history preserved; outreach and reply sending are disabled.", flush=True)
            print("No Gmail connection, schedule, or email send was activated. Restart the command center.", flush=True)
    finally:
        os.umask(old_umask)
