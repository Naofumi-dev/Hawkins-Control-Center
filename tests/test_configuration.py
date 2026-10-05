"""Synthetic credential setup checks. No real keys, mail, or provider requests."""
import base64
import contextlib
import copy
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from client_finder.configuration import (
    ConfigurationError, configure, load_private_environment, save_private_environment,
    valid_api_key, verify_connection,
)
from client_finder.gmail import OWNER_EMAIL
from client_finder.providers import EXPECTED_SUPABASE_URL, ProviderError, SupabaseRest


OWNER_ID = "11111111-1111-4111-8111-111111111111"
VALUES = {
    "SUPABASE_URL": EXPECTED_SUPABASE_URL,
    "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_synthetic_not_a_real_key",
    "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_synthetic_not_a_real_key",
    "CLIENT_FINDER_OWNER_AUTH_ID": OWNER_ID,
    "CLIENT_FINDER_SERVICE_TOKEN": "synthetic_not_a_real_service_token_123456",
}
USER = {"id": OWNER_ID, "email": OWNER_EMAIL, "email_confirmed_at": "2026-10-05T00:00:00Z"}
AUTH = {"external": {"email": True}, "disable_signup": True}


def legacy_key(role, ref="mtdavgadkiiofwikzdtn"):
    payload = base64.urlsafe_b64encode(json.dumps({"role": role, "ref": ref}).encode()).decode().rstrip("=")
    return "synthetic." + payload + ".not_a_signature"


class ConnectionValidationTests(unittest.TestCase):
    def test_verification_is_get_only_and_bound_to_owned_project(self):
        with patch("client_finder.configuration._json_request", side_effect=[USER, AUTH]) as request:
            self.assertEqual(verify_connection(VALUES), {"signups_disabled": True})
        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            self.assertTrue(call.args[0].startswith(EXPECTED_SUPABASE_URL + "/auth/v1/"))
            self.assertNotIn("payload", call.kwargs)
            self.assertNotIn("method", call.kwargs)
            self.assertNotIn("Authorization", call.kwargs["headers"])
        self.assertTrue(request.call_args_list[0].args[0].endswith("/admin/users/" + OWNER_ID))

    def test_wrong_project_or_wrong_key_kind_is_rejected_before_network(self):
        variants = [
            {"SUPABASE_URL": "https://another-project.supabase.co"},
            {"SUPABASE_PUBLISHABLE_KEY": VALUES["SUPABASE_SERVICE_ROLE_KEY"]},
            {"SUPABASE_SERVICE_ROLE_KEY": VALUES["SUPABASE_PUBLISHABLE_KEY"]},
            {"SUPABASE_PUBLISHABLE_KEY": legacy_key("anon", "another-project")},
            {"SUPABASE_SERVICE_ROLE_KEY": legacy_key("service_role", "another-project")},
        ]
        for changes in variants:
            with self.subTest(field=next(iter(changes))), patch("client_finder.configuration._json_request") as request:
                with self.assertRaises(ConfigurationError):
                    verify_connection({**VALUES, **changes})
                request.assert_not_called()

    def test_wrong_or_unconfirmed_owner_stops_before_public_key_check(self):
        for changes in ({"id": "22222222-2222-4222-8222-222222222222"},
                        {"email": "wrong@example.test"}, {"email_confirmed_at": None}):
            with self.subTest(field=next(iter(changes))), patch(
                "client_finder.configuration._json_request", return_value={**USER, **changes}
            ) as request:
                with self.assertRaises(ConfigurationError):
                    verify_connection(VALUES)
                self.assertEqual(request.call_count, 1)

    def test_legacy_headers_remain_compatible_and_new_secret_is_not_a_bearer(self):
        legacy = legacy_key("service_role")
        self.assertEqual(SupabaseRest(EXPECTED_SUPABASE_URL, legacy).headers["Authorization"], "Bearer " + legacy)
        self.assertNotIn("Authorization", SupabaseRest(EXPECTED_SUPABASE_URL, VALUES["SUPABASE_SERVICE_ROLE_KEY"]).headers)

    def test_malformed_or_privileged_key_is_never_public(self):
        for key in ("", "sb_secret_hidden_secret", legacy_key("service_role"), "x.%%%%.x", "x.W10.x", "sb_publishable_line\nbreak"):
            with self.subTest(shape=key.split(".")[0]):
                self.assertFalse(valid_api_key(key, public=True))
        self.assertTrue(valid_api_key(legacy_key("anon"), public=True))


class PrivateFileTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="hawkins-setup-test-")
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "private" / "connection.json"

    def test_save_is_private_load_is_allowlisted_and_host_override_is_preserved(self):
        save_private_environment(self.path, VALUES)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)
        token = "synthetic_host_token_preserved_123456789"
        with patch.dict(os.environ, {"CLIENT_FINDER_SERVICE_TOKEN": token}, clear=True):
            load_private_environment(self.path)
            self.assertEqual(os.environ["SUPABASE_URL"], EXPECTED_SUPABASE_URL)
            self.assertEqual(os.environ["CLIENT_FINDER_OWNER_AUTH_ID"], OWNER_ID)
            self.assertEqual(os.environ["CLIENT_FINDER_SERVICE_TOKEN"], token)
            self.assertEqual(set(os.environ), set(VALUES))

    def test_existing_file_is_not_overwritten(self):
        save_private_environment(self.path, VALUES)
        original = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            save_private_environment(self.path, {**VALUES, "CLIENT_FINDER_OWNER_AUTH_ID": "22222222-2222-4222-8222-222222222222"})
        self.assertEqual(self.path.read_bytes(), original)

    def test_wrong_project_override_does_not_partially_load_keys(self):
        save_private_environment(self.path, VALUES)
        with patch.dict(os.environ, {"SUPABASE_URL": "https://another-project.supabase.co"}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_private_environment(self.path)
            self.assertNotIn("SUPABASE_SERVICE_ROLE_KEY", os.environ)

    def test_publicly_readable_file_or_parent_is_rejected(self):
        save_private_environment(self.path, VALUES)
        for target, permissions in ((self.path, 0o644), (self.path.parent, 0o755)):
            with self.subTest(target=target.name):
                old = stat.S_IMODE(target.stat().st_mode)
                target.chmod(permissions)
                with self.assertRaises(ConfigurationError):
                    load_private_environment(self.path)
                target.chmod(old)

    def test_symlink_cannot_be_read_or_overwritten(self):
        save_private_environment(self.path, VALUES)
        link = self.path.with_name("link.json")
        link.symlink_to(self.path)
        with self.assertRaises(OSError):
            load_private_environment(link)
        with self.assertRaises(FileExistsError):
            save_private_environment(link, VALUES)

    def test_source_tree_storage_is_rejected(self):
        path = Path(__file__).resolve().parents[1] / "artifacts" / "connection.json"
        with self.assertRaises(ConfigurationError):
            save_private_environment(path, VALUES)
        self.assertFalse(path.exists())

    def test_extra_environment_keys_and_invalid_json_do_not_load(self):
        save_private_environment(self.path, VALUES)
        documents = ["not json", json.dumps({"version": 1, "environment": {**VALUES, "PATH": "/tmp"}})]
        for content in documents:
            self.path.write_text(content)
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigurationError):
                    load_private_environment(self.path)
                self.assertEqual(dict(os.environ), {})

    def test_successful_interactive_setup_never_prints_keys_or_calls_writes(self):
        output = io.StringIO()
        with patch("client_finder.configuration.getpass.getpass", side_effect=[
            VALUES["SUPABASE_PUBLISHABLE_KEY"], VALUES["SUPABASE_SERVICE_ROLE_KEY"]
        ]), patch("client_finder.configuration._json_request", side_effect=[copy.deepcopy(USER), AUTH]), \
             patch("client_finder.configuration.SupabaseRest.rows", side_effect=ProviderError("unavailable")), \
             contextlib.redirect_stdout(output):
            configure(OWNER_ID, self.path)
        self.assertTrue(self.path.exists())
        self.assertIn("Confirmed personal owner", output.getvalue())
        self.assertIn("Inbox schema could not be verified", output.getvalue())
        for name in ("SUPABASE_PUBLISHABLE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "CLIENT_FINDER_SERVICE_TOKEN"):
            self.assertNotIn(VALUES[name], output.getvalue())

    def test_failed_owner_verification_never_saves_credentials(self):
        with patch("client_finder.configuration.getpass.getpass", side_effect=[
            VALUES["SUPABASE_PUBLISHABLE_KEY"], VALUES["SUPABASE_SERVICE_ROLE_KEY"]
        ]), patch("client_finder.configuration._json_request", return_value={**USER, "email": "wrong@example.test"}), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ConfigurationError):
                configure(OWNER_ID, self.path)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
