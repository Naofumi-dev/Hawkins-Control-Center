import unittest
from unittest.mock import Mock, patch

from client_finder.control_center import ControlCenter
from client_finder.providers import EXPECTED_SUPABASE_URL, ProviderError, SupabaseRest, _NoRedirects


LEAD_ID = "11111111-1111-4111-8111-111111111111"
OPPORTUNITY_ID = "22222222-2222-4222-8222-222222222222"


class WorkspaceCatalogTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.api = ControlCenter(self.db, LEAD_ID)

    def test_page_preserves_total_and_uses_validated_keyset_cursor(self):
        self.db.count.return_value = 231
        self.db.rows.return_value = [{"id": str(i)} for i in range(100)]
        page = self.api.leads(after_id=LEAD_ID)
        self.assertEqual(page["total"], 231)
        self.assertEqual(page["next_after"], "99")
        self.assertNotIn("id", self.db.count.call_args.args[1])
        filters = self.db.rows.call_args.args[1]
        self.assertEqual(filters["id"], "gt."+LEAD_ID)
        self.assertEqual(filters["limit"], "100")
        self.assertEqual(filters["order"], "id.asc")

    def test_search_quotes_filter_punctuation_as_data(self):
        self.db.rows.return_value = []
        self.api.leads('A "B",(C)\\D')
        query = self.db.rows.call_args.args[1]["or"]
        self.assertIn('company_name.ilike."%A \\"B\\",(C)\\\\D%"', query)
        self.assertEqual(query.count('.ilike.'), 6)

    def test_invalid_cursor_and_history_do_not_read_rows(self):
        for kwargs in ({"after_id": "x),status.eq.sent"}, {"history": "sent,all"}, {"search": "x"*161}, {"search": "a\nb"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.api.leads(**kwargs)
        self.db.rows.assert_not_called()

    def test_contact_history_is_not_inferred_from_a_model_category(self):
        self.db.rows.return_value = []
        self.api.leads(history="contacted")
        self.assertEqual(self.db.rows.call_args.args[1]["first_sent_at"], "not.is.null")
        self.api.leads(history="replied")
        self.assertEqual(self.db.rows.call_args.args[1]["replied_at"], "not.is.null")

    def test_lead_details_keep_suppression_and_match_via_linked_opportunity(self):
        def rows(table, filters, **kwargs):
            if table == "cold_leads":
                return [{"id": LEAD_ID, "contact_email": "contact@agency.example", "company_domain": "agency.example"}]
            if table == "client_finder_opportunities":
                return [{"id": OPPORTUNITY_ID}]
            if table == "client_finder_suppressions":
                return [{"scope": filters["scope"][3:], "reason": "Owner request"}]
            return []
        self.db.rows.side_effect = rows
        detail = self.api.lead(LEAD_ID)
        self.assertEqual(len(detail["suppressions"]), 2)
        self.db.rows.assert_any_call("client_finder_conversations", {"opportunity_id": "in.("+OPPORTUNITY_ID+")"})
        self.db.rpc.assert_not_called()
        self.db.insert.assert_not_called()

    def test_library_preserves_inactive_and_unverified_items_without_private_workbook_path(self):
        self.db.rows.return_value = [{"id": "proof", "active": False, "verified_at": None}]
        library = self.api.library()
        self.assertEqual(len(library["sources"]), 169)
        self.assertEqual(library["source_rows"], 393)
        self.assertFalse(library["proofs"][0]["active"])
        for call in self.db.rows.call_args_list:
            self.assertNotIn("active", call.args[1])
        self.assertNotIn("source_workbook", library)
        self.assertNotIn("source_rows", library["sources"][0])

    def test_overview_does_not_hide_provider_failure_as_zero(self):
        self.db.count.side_effect = ProviderError("Unavailable")
        with self.assertRaises(ProviderError):
            self.api.overview()


class ExactCountTests(unittest.TestCase):
    def test_head_count_uses_owned_project_and_no_redirects(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.headers = {"Content-Range": "*/231"}
        opener = Mock()
        opener.open.return_value = response
        with patch("client_finder.providers.urllib.request.build_opener", return_value=opener) as build:
            self.assertEqual(SupabaseRest(EXPECTED_SUPABASE_URL, "test-only-key").count("cold_leads"), 231)
        self.assertIsInstance(build.call_args.args[0], _NoRedirects)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.method, "HEAD")
        self.assertEqual(request.headers["Prefer"], "count=exact")
        self.assertTrue(request.full_url.startswith(EXPECTED_SUPABASE_URL + "/rest/v1/cold_leads?"))
        response.read.assert_not_called()

    def test_unknown_count_is_an_error(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.headers = {"Content-Range": "0-99/*"}
        with patch("client_finder.providers.urllib.request.build_opener") as build:
            build.return_value.open.return_value = response
            with self.assertRaises(ProviderError):
                SupabaseRest(EXPECTED_SUPABASE_URL, "test-only-key").count("cold_leads")
