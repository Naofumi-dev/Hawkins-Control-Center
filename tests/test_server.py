import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from client_finder.server import Handler


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class ServiceRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, path, payload, token="secret"):
        data = json.dumps(payload).encode()
        req = urllib.request.Request(self.url + path, data=data, headers={
            "Authorization": f"Bearer {token}", "Content-Type": "application/json"
        })
        try:
            with urllib.request.urlopen(req, timeout=2) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, json.load(exc)

    def test_mail_poll_requires_service_token_and_returns_checkpointed_result(self):
        with patch.dict(os.environ, {
            "CLIENT_FINDER_SERVICE_TOKEN": "secret", "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "fake-key", "BRAVE_SEARCH_API_KEY": "fake-brave",
        }), patch("client_finder.server.build_database", return_value=object()), patch(
            "client_finder.server.MailMonitor.poll", return_value={"status": "complete", "results": [], "checkpoint": {"last_success_at": "now"}}
        ) as poll:
            self.assertEqual(self.request("/mail-poll", {}, token="wrong")[0], 401)
            status, result = self.request("/mail-poll", {
                "gmail_messages": [], "scanned_since": "2026-09-27T00:00:00Z", "scanned_until": "2026-09-27T01:00:00Z"
            })
            self.assertEqual(status, 200)
            self.assertEqual(result["status"], "complete")
            poll.assert_called_once()

    def test_missing_configuration_fails_closed(self):
        with patch.dict(os.environ, {"CLIENT_FINDER_SERVICE_TOKEN": "secret"}, clear=True):
            status, result = self.request("/discover", {"limit": 5})
            self.assertEqual(status, 503)
            self.assertEqual(result["error"], "provider_or_configuration_unavailable")

    def test_health_rejects_wrong_supabase_project_even_with_all_keys_present(self):
        with patch.dict(os.environ, {
            "CLIENT_FINDER_SERVICE_TOKEN": "secret", "SUPABASE_URL": "https://other-project.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "fake-key", "BRAVE_SEARCH_API_KEY": "fake-brave",
        }, clear=True):
            try:
                with urllib.request.urlopen(self.url + "/health", timeout=2) as response:
                    status, result = response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                with exc:
                    status, result = exc.code, json.load(exc)
            self.assertEqual(status, 503)
            self.assertEqual(result["status"], "setup_incomplete")

    def test_public_config_requires_backend_and_never_exposes_server_keys(self):
        values = {
            "SUPABASE_URL": "https://mtdavgadkiiofwikzdtn.supabase.co",
            "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_synthetic_not_a_real_key",
            "SUPABASE_SERVICE_ROLE_KEY": "sb_secret_synthetic_not_a_real_key",
            "CLIENT_FINDER_SERVICE_TOKEN": "synthetic_private_service_token",
            "CLIENT_FINDER_OWNER_AUTH_ID": "11111111-1111-4111-8111-111111111111",
        }
        cases = [(values, True), ({**values, "SUPABASE_SERVICE_ROLE_KEY": ""}, False),
                 ({**values, "SUPABASE_URL": "https://another-project.supabase.co"}, False),
                 ({**values, "SUPABASE_PUBLISHABLE_KEY": values["SUPABASE_SERVICE_ROLE_KEY"]}, False)]
        for environment, configured in cases:
            with self.subTest(configured=configured), patch.dict(os.environ, environment, clear=True):
                with urllib.request.urlopen(self.url + "/api/config", timeout=2) as response:
                    result = json.load(response)
            self.assertEqual(result["configured"], configured)
            self.assertNotIn(values["SUPABASE_SERVICE_ROLE_KEY"], json.dumps(result))
            self.assertNotIn(values["CLIENT_FINDER_SERVICE_TOKEN"], json.dumps(result))

    def test_catalog_routes_require_owner_before_reading_records(self):
        from client_finder.control_center import OwnerError
        with patch("client_finder.server.build_database"), patch("client_finder.server.authenticate_owner", side_effect=OwnerError), patch("client_finder.server.ControlCenter") as api:
            for path in ("/api/overview", "/api/leads", "/api/leads/11111111-1111-4111-8111-111111111111", "/api/library"):
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as exc:
                    urllib.request.urlopen(self.url + path, timeout=2)
                self.assertEqual(exc.exception.code, 403)
                exc.exception.close()
            api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
