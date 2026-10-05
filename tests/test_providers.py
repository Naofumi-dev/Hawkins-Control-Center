import unittest
from unittest.mock import MagicMock, patch

from client_finder.providers import (
    BraveSearch, EXPECTED_SUPABASE_URL, ProviderConfigurationError,
    ProviderError, SupabaseRest, _NoRedirects, _json_request,
)


class FakeBudget:
    def __init__(self, *, fail_reserve=False):
        self.events = []
        self.fail_reserve = fail_reserve

    def reserve_cost(self, provider, operation, max_cost_cents):
        self.events.append(("reserve", provider, operation, max_cost_cents))
        if self.fail_reserve:
            raise ProviderError("Monthly limit reached")
        return "reservation-1"

    def begin_cost_call(self, reservation_id):
        self.events.append(("begin", reservation_id))

    def settle_cost(self, reservation_id, actual_cents):
        self.events.append(("settle", reservation_id, actual_cents))


class PaidSearchTests(unittest.TestCase):
    def test_paid_call_is_blocked_if_reservation_fails(self):
        budget = FakeBudget(fail_reserve=True)
        with patch("client_finder.providers._json_request") as request:
            with self.assertRaises(ProviderError):
                BraveSearch("test-key", budget).search("agency client portals")
        request.assert_not_called()
        self.assertEqual(len(budget.events), 1)

    def test_successful_call_reserves_and_settles_half_cent(self):
        budget = FakeBudget()
        payload = {"web": {"results": [{"title": "Atlas", "url": "https://atlas.example", "description": "Agency"}]}}
        with patch("client_finder.providers._json_request", return_value=payload):
            hits = BraveSearch("test-key", budget).search("agency client portals")
        self.assertEqual(len(hits), 1)
        self.assertEqual([event[0] for event in budget.events], ["reserve", "begin", "settle"])
        self.assertEqual(budget.events[0][-1], 0.5)
        self.assertEqual(budget.events[2][-1], 0.5)

    def test_uncertain_provider_timeout_keeps_cost_reserved(self):
        budget = FakeBudget()
        with patch("client_finder.providers._json_request", side_effect=ProviderError("Provider request failed")):
            with self.assertRaises(ProviderError):
                BraveSearch("test-key", budget).search("agency client portals")
        self.assertEqual([event[0] for event in budget.events], ["reserve", "begin"])


class ProviderDestinationTests(unittest.TestCase):
    def test_successful_void_rpc_accepts_no_content_without_retry(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status, response.read.return_value = 204, b""
        with patch("client_finder.providers.urllib.request.build_opener", return_value=opener):
            result = SupabaseRest(EXPECTED_SUPABASE_URL, "test-only-key").rpc(
                "client_finder_task_finish", {"task_id": "synthetic-task"})
        self.assertIsNone(result)
        self.assertEqual(opener.open.call_count, 1)

    def test_empty_json_success_response_still_fails_closed(self):
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status, response.read.return_value = 200, b""
        with patch("client_finder.providers.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ProviderError):
                _json_request("https://api.example.test/data")

    def test_supabase_must_be_the_owned_project(self):
        for url in ("https://other-project.supabase.co", "http://mtdavgadkiiofwikzdtn.supabase.co",
                    EXPECTED_SUPABASE_URL + "/rest/v1", EXPECTED_SUPABASE_URL + "?other=1"):
            with self.subTest(url=url), self.assertRaises(ProviderConfigurationError):
                SupabaseRest(url, "test-only-key")
        self.assertEqual(SupabaseRest(EXPECTED_SUPABASE_URL + "/", "test-only-key").url,
                         EXPECTED_SUPABASE_URL)
        with self.assertRaises(ProviderConfigurationError):
            SupabaseRest(EXPECTED_SUPABASE_URL, " ")

    def test_credentialed_requests_use_an_opener_that_refuses_redirects(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _limit):
                return b"{}"

        class Opener:
            def open(self, request, timeout):
                self.request = request
                return Response()

        opener = Opener()
        with patch("client_finder.providers.urllib.request.build_opener", return_value=opener) as build:
            self.assertEqual(_json_request("https://api.example.test/data", headers={
                "Authorization": "Bearer test-only-key"}), {})
        redirect_handler = build.call_args.args[0]
        self.assertIsInstance(redirect_handler, _NoRedirects)
        self.assertIsNone(redirect_handler.redirect_request(
            opener.request, None, 302, "Found", {}, "https://different.example.test/collect"))


if __name__ == "__main__":
    unittest.main()
