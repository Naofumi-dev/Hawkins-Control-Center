"""Synthetic backup/migration gates. Never connect to a live database."""
import contextlib
import io
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from client_finder.database_setup import (
    CA_FILE, DatabaseSetupError, HISTORY_SQL, PG_HOST, PG_USER, migration_body, migration_bundle,
    pg_environment, prepare_database, run_client, write_password_file,
)


class DatabaseSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hawkins-database-test-")
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.tools = {name: name for name in ("psql", "pg_dump", "pg_restore")}
        self.history = {"leads": 3, "campaigns": 1, "suppressions": 1, "send_attempts": 0}
        self.identity = {"owner_verified": True, "version": 170006, "outreach_disabled": True, "new_table_count": 0}
        self.events = []

    def fake_client(self, command, environment, *, sql=None, stage):
        self.events.append((stage, command, sql))
        if stage == "Database preflight":
            statement = command[-1]
            if "owner_verified" in statement:
                return json.dumps(self.identity)
            if statement == HISTORY_SQL:
                return json.dumps(self.history)
            return '[{"result":"PASS"}]'
        if stage == "Database backup":
            (self.directory / "before-inbox.dump").write_bytes(b"synthetic archive, not a real database")
        if stage == "Backup inventory":
            return "\n".join("0 0 0 " + kind + " public " + table + " postgres" for table in (
                "cold_leads", "cold_campaigns", "client_finder_settings", "client_finder_suppressions", "client_finder_send_attempts"
            ) for kind in ("TABLE", "TABLE DATA"))
        return ""

    @contextlib.contextmanager
    def setup_context(self, client=None):
        with patch("client_finder.database_setup.verify_connection"), \
             patch("client_finder.database_setup.client_tools", return_value=self.tools), \
             patch("client_finder.database_setup.backup_directory", return_value=self.directory), \
             patch("client_finder.database_setup.getpass.getpass", return_value="synthetic_password"), \
             patch("client_finder.database_setup.run_client", side_effect=client or self.fake_client), \
             patch.dict(os.environ, {"CLIENT_FINDER_OWNER_AUTH_ID": "11111111-1111-4111-8111-111111111111"}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            yield output

    def test_host_tls_and_password_file_override_unrelated_pg_environment(self):
        with patch.dict(os.environ, {"PGHOST": "other.invalid", "PGSERVICE": "wrong", "PGPASSWORD": "wrong", "PGSSLMODE": "disable"}):
            environment = pg_environment(self.directory / "pgpass")
        self.assertEqual(environment["PGHOST"], PG_HOST)
        self.assertEqual(environment["PGUSER"], PG_USER)
        self.assertEqual(environment["PGSSLMODE"], "verify-full")
        self.assertEqual(environment["PGSSLROOTCERT"], str(CA_FILE))
        self.assertNotIn("PGSERVICE", environment)
        self.assertNotIn("PGPASSWORD", environment)

    def test_changed_ca_is_rejected_before_any_database_connection(self):
        with patch("client_finder.database_setup.CA_SHA256", "invalid"):
            with self.assertRaisesRegex(DatabaseSetupError, "root certificate"):
                pg_environment(self.directory / "pgpass")

    def test_password_file_is_private_escaped_and_never_overwritten(self):
        path = self.directory / "pgpass"
        write_password_file(path, "synthetic:pass\\word")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertIn("synthetic\\:pass\\\\word", path.read_text())
        with self.assertRaises(FileExistsError):
            write_password_file(path, "different")
        with self.assertRaises(DatabaseSetupError):
            write_password_file(self.directory / "bad", "line\nbreak")

    def test_errors_do_not_disclose_private_provider_output(self):
        result = subprocess.CompletedProcess([], 1, "", "password authentication failed: synthetic_secret")
        with patch("client_finder.database_setup.subprocess.run", return_value=result):
            with self.assertRaisesRegex(DatabaseSetupError, "database_password_rejected") as caught:
                run_client(["psql"], {}, stage="Preflight")
        self.assertNotIn("synthetic_secret", str(caught.exception))

    def test_backup_only_never_applies_migrations_and_removes_password(self):
        with self.setup_context() as output:
            prepare_database()
        self.assertNotIn("Inbox migration transaction", [event[0] for event in self.events])
        self.assertEqual(list(self.directory.glob("credential-*")), [])
        self.assertNotIn("synthetic_password", output.getvalue())
        manifest = json.loads((self.directory / "manifest.json").read_text())
        self.assertTrue(manifest["archive_decoded"])
        self.assertFalse(manifest["restore_tested"])
        self.assertEqual(manifest["migration_status"], "not_applied")

    def test_backup_failure_prevents_migration_and_removes_password(self):
        def fail_backup(command, environment, *, sql=None, stage):
            if stage == "Database backup":
                raise DatabaseSetupError("Backup unavailable")
            return self.fake_client(command, environment, sql=sql, stage=stage)
        with self.setup_context(fail_backup):
            with self.assertRaises(DatabaseSetupError):
                prepare_database(apply=True)
        self.assertNotIn("Inbox migration transaction", [event[0] for event in self.events])
        self.assertEqual(list(self.directory.glob("credential-*")), [])

    def test_archive_missing_table_data_prevents_migration(self):
        def incomplete(command, environment, *, sql=None, stage):
            result = self.fake_client(command, environment, sql=sql, stage=stage)
            return result.replace("TABLE DATA public cold_leads", "MISSING") if stage == "Backup inventory" else result
        with self.setup_context(incomplete):
            with self.assertRaisesRegex(DatabaseSetupError, "missing required"):
                prepare_database(apply=True)
        self.assertNotIn("Inbox migration transaction", [event[0] for event in self.events])

    def test_wrong_owner_active_sending_and_partial_install_stop_before_backup(self):
        for changes in ({"owner_verified": False}, {"outreach_disabled": False}, {"new_table_count": 1}):
            with self.subTest(changes=changes):
                self.identity = {"owner_verified": True, "version": 170006, "outreach_disabled": True, "new_table_count": 0, **changes}
                self.events.clear()
                with self.setup_context():
                    with self.assertRaises(DatabaseSetupError):
                        prepare_database(apply=True)
                self.assertNotIn("Database backup", [event[0] for event in self.events])

    def test_apply_waits_for_verified_backup_and_uses_one_transaction(self):
        with self.setup_context():
            prepare_database(apply=True)
        stages = [event[0] for event in self.events]
        self.assertLess(stages.index("Backup content validation"), stages.index("Inbox migration transaction"))
        migration = self.events[-1]
        self.assertIn("--single-transaction", migration[1])
        self.assertIn("personal_postflight_1_failed", migration[2])
        self.assertIn("legacy_history_changed", migration[2])
        self.assertNotRegex(migration[2], r"(?m)^(?:begin|commit);\s*$")
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text())["migration_status"], "committed_with_postflight_checks")

    def test_unknown_migration_result_keeps_backup_and_requires_inspection(self):
        def uncertain(command, environment, *, sql=None, stage):
            if stage == "Inbox migration transaction":
                raise DatabaseSetupError("Result unconfirmed")
            return self.fake_client(command, environment, sql=sql, stage=stage)
        with self.setup_context(uncertain):
            with self.assertRaises(DatabaseSetupError):
                prepare_database(apply=True)
        self.assertTrue((self.directory / "before-inbox.dump").is_file())
        manifest = json.loads((self.directory / "manifest.json").read_text())
        self.assertEqual(manifest["migration_status"], "started_outcome_unconfirmed")
        self.assertEqual(list(self.directory.glob("credential-*")), [])

    def test_bundle_refuses_unexpected_transaction_layout_and_invalid_counts(self):
        with self.assertRaises(DatabaseSetupError):
            migration_body("begin;\nselect 1;\ncommit;\nbegin;\ncommit;")
        with self.assertRaises(DatabaseSetupError):
            migration_bundle({**self.history, "leads": "0;drop table anything"})


if __name__ == "__main__":
    unittest.main()
