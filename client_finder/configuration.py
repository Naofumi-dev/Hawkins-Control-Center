"""Private, owner-verified local connection setup. No mail or database writes."""
from __future__ import annotations

import base64
import getpass
import json
import os
import re
import secrets
import stat
import uuid
import warnings
from pathlib import Path

from .gmail import OWNER_EMAIL
from .providers import EXPECTED_SUPABASE_URL, ProviderError, SupabaseRest, _json_request, supabase_headers


class ConfigurationError(ValueError):
    pass


CONFIG_KEYS = frozenset({
    "SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SERVICE_ROLE_KEY",
    "CLIENT_FINDER_OWNER_AUTH_ID", "CLIENT_FINDER_SERVICE_TOKEN",
})
PROJECT_REF = "mtdavgadkiiofwikzdtn"


def default_config_path() -> Path:
    return Path.home() / ".config" / "hawkins-personal" / "connection.json"


def valid_api_key(key: str, *, public: bool) -> bool:
    """Check key kind and legacy project claims; live verification is still required."""
    if not isinstance(key, str) or not 20 <= len(key) <= 8192 or re.search(r"\s", key):
        return False
    prefix = "sb_publishable_" if public else "sb_secret_"
    if re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9_-]+", key):
        return True
    try:
        parts = key.split(".")
        if len(parts) != 3:
            return False
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return (isinstance(claims, dict) and claims.get("ref") == PROJECT_REF and
                claims.get("role") == ("anon" if public else "service_role"))
    except (ValueError, UnicodeError):
        return False


def validate_environment(values: dict) -> None:
    if (not isinstance(values, dict) or set(values) != CONFIG_KEYS or
            any(not isinstance(v, str) for v in values.values())):
        raise ConfigurationError("Private connection file has an invalid format")
    if values["SUPABASE_URL"] != EXPECTED_SUPABASE_URL:
        raise ConfigurationError("Only the personal Hawkins project is allowed")
    try:
        uid = str(uuid.UUID(values["CLIENT_FINDER_OWNER_AUTH_ID"]))
    except ValueError:
        raise ConfigurationError("Owner Auth user ID must be a UUID") from None
    if uid != values["CLIENT_FINDER_OWNER_AUTH_ID"]:
        raise ConfigurationError("Owner Auth user ID must be a canonical UUID")
    if not valid_api_key(values["SUPABASE_PUBLISHABLE_KEY"], public=True):
        raise ConfigurationError("Use the personal project's publishable or anon key")
    if not valid_api_key(values["SUPABASE_SERVICE_ROLE_KEY"], public=False):
        raise ConfigurationError("Use the personal project's server secret or service_role key")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", values["CLIENT_FINDER_SERVICE_TOKEN"]):
        raise ConfigurationError("Private service token is invalid")


def verify_connection(values: dict) -> dict:
    """GET requests only, bound to the owned project before any credentials leave."""
    validate_environment(values)
    owner_id = values["CLIENT_FINDER_OWNER_AUTH_ID"]
    user = _json_request(EXPECTED_SUPABASE_URL + "/auth/v1/admin/users/" + owner_id,
                         headers=supabase_headers(values["SUPABASE_SERVICE_ROLE_KEY"]))
    if (not isinstance(user, dict) or user.get("id") != owner_id or
            str(user.get("email", "")).lower() != OWNER_EMAIL or not user.get("email_confirmed_at")):
        raise ConfigurationError("The confirmed personal owner was not verified; nothing was saved")
    settings = _json_request(EXPECTED_SUPABASE_URL + "/auth/v1/settings",
                             headers=supabase_headers(values["SUPABASE_PUBLISHABLE_KEY"]))
    if not isinstance(settings, dict) or not isinstance(settings.get("external"), dict):
        raise ConfigurationError("Public Auth connection was not verified; nothing was saved")
    return {"signups_disabled": settings.get("disable_signup") is True}


def _check_location(path: Path) -> None:
    if path.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ConfigurationError("Keep the private connection file outside the source workspace")
    if path.parent.is_symlink():
        raise ConfigurationError("The private connection directory must not be a symlink")
    parent = path.parent.stat()
    if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) & 0o077:
        raise ConfigurationError("The private connection directory must belong to you with mode 700")


def save_private_environment(path: Path, values: dict) -> None:
    validate_environment(values)
    # Do not follow a supplied path into the source tree, even on first setup.
    if path.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ConfigurationError("Keep the private connection file outside the source workspace")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _check_location(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "w") as file:
            json.dump({"version": 1, "environment": values}, file)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def load_private_environment(path: Path | None = None) -> None:
    """Allow host environment overrides; never execute a shell or load arbitrary names."""
    explicit = path is not None
    path = path or default_config_path()
    if not explicit and not path.exists() and not path.is_symlink():
        return
    _check_location(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor) as file:
        info = os.fstat(file.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
                stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1 or info.st_size > 24000):
            raise ConfigurationError("Private connection file must be an owned, unshared regular file with mode 600")
        try:
            document = json.loads(file.read(24001))
        except (ValueError, UnicodeError):
            raise ConfigurationError("Private connection file is invalid") from None
    if not isinstance(document, dict) or document.get("version") != 1 or set(document) != {"version", "environment"}:
        raise ConfigurationError("Private connection file has an unsupported format")
    values = document["environment"]
    validate_environment(values)
    merged = {name: os.environ.get(name, value) for name, value in values.items()}
    validate_environment(merged)
    os.environ.update(merged)


def configure(owner_id: str, path: Path | None = None) -> None:
    path = path or default_config_path()
    if path.exists() or path.is_symlink():
        raise ConfigurationError("A private connection file already exists; it was not overwritten")
    try:
        owner_id = str(uuid.UUID(owner_id))
    except ValueError:
        raise ConfigurationError("Use the confirmed owner's Auth user UUID") from None
    print("Personal Hawkins only: " + OWNER_EMAIL)
    print("Project: " + PROJECT_REF)
    print("Paste keys from this project's Settings > API Keys. Input is hidden.")
    with warnings.catch_warnings():
        # getpass must never fall back to echoing a secret into a log or pipe.
        warnings.simplefilter("error", getpass.GetPassWarning)
        public = getpass.getpass("Publishable / anon key: ").strip()
        server = getpass.getpass("Server secret / service_role key: ").strip()
    values = {
        "SUPABASE_URL": EXPECTED_SUPABASE_URL,
        "SUPABASE_PUBLISHABLE_KEY": public,
        "SUPABASE_SERVICE_ROLE_KEY": server,
        "CLIENT_FINDER_OWNER_AUTH_ID": owner_id,
        "CLIENT_FINDER_SERVICE_TOKEN": secrets.token_urlsafe(48),
    }
    result = verify_connection(values)
    save_private_environment(path, values)
    print("Confirmed personal owner and both API keys verified. Private connection saved.")
    if not result["signups_disabled"]:
        print("Public signups are still enabled in Supabase. Review Auth settings before deployment.")
    database = SupabaseRest(values["SUPABASE_URL"], server)
    try:
        database.rows("client_finder_mailboxes", {"limit": "1"}, select="email")
        print("Inbox table is reachable. This does not verify migrations, Gmail, or sending.")
    except ProviderError:
        print("Inbox schema could not be verified. Complete the backup and migration checks before use.")
    print("Restart the command center to load the connection. No mail was read or sent.")
