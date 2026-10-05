"""The research preview must fail clearly before any paid search when setup is missing."""

import contextlib
import io
import os
import sys
import unittest
from unittest.mock import patch

from client_finder.__main__ import main


class PreviewCliTests(unittest.TestCase):
    def test_missing_configuration_reports_names_without_starting_search(self):
        stderr = io.StringIO()
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, "argv", ["client_finder", "preview"]), \
             patch("client_finder.__main__.load_private_environment"), \
             patch("client_finder.__main__.build_runner") as runner, contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as exit_result:
                main()
        self.assertEqual(exit_result.exception.code, 2)
        self.assertIn("SUPABASE_URL", stderr.getvalue())
        self.assertIn("BRAVE_SEARCH_API_KEY", stderr.getvalue())
        runner.assert_not_called()

    def test_configure_provider_failure_is_sanitized(self):
        from client_finder.providers import ProviderError
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["client_finder", "configure", "--owner-id", "11111111-1111-4111-8111-111111111111"]), \
             patch("client_finder.__main__.configure", side_effect=ProviderError("synthetic_private_key")), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as result:
                main()
        self.assertEqual(result.exception.code, 2)
        self.assertNotIn("synthetic_private_key", stderr.getvalue())

    def test_serve_loads_private_configuration_before_starting(self):
        events = []
        with patch.object(sys, "argv", ["client_finder", "serve"]), \
             patch("client_finder.__main__.load_private_environment", side_effect=lambda _: events.append("load")), \
             patch("client_finder.__main__.serve", side_effect=lambda: events.append("serve")):
            main()
        self.assertEqual(events, ["load", "serve"])


if __name__ == "__main__":
    unittest.main()
