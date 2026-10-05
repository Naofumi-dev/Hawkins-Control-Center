import unittest
from unittest.mock import patch

from client_finder.discovery import DiscoveryRunner
from client_finder.providers import SearchResult
from client_finder.research import parse_page


class FakeDatabase:
    def __init__(self, *, sender=True, existing=None):
        self.settings = {
            "discovery_enabled": True,
            "sender_name": "Armageddon Vivas" if sender else None,
            "postal_address": "123 Main Street, Springfield, MA 01101" if sender else None,
            "commercial_label": "Service offer" if sender else None,
            "opt_out_route": "Reply no to opt out" if sender else None,
        }
        self.existing = existing
        self.created = []
        self.messages = []
        self.research_tasks = []

    def rows(self, table, filters, *, select="*"):
        if table == "client_finder_settings":
            return [self.settings]
        if table == "cold_leads":
            if "company_domain" in filters and self.existing:
                return [self.existing]
            return []
        if table == "client_finder_messages":
            return []
        raise AssertionError(table)

    def insert(self, table, values):
        assert table == "cold_leads"
        self.created.append(values)
        return {"id": "lead-1", **values}

    def rpc(self, name, values):
        if name == "client_finder_record_research_task":
            self.research_tasks.append(values)
            return {"domain": values["domain"], "status": "open"}
        assert name == "client_finder_create_message"
        self.messages.append(values)
        return {"id": "message-1", "revision": 1}


class FakeSearch:
    def __init__(self):
        self.count = 0

    def search(self, query):
        self.count += 1
        return [SearchResult("Atlas Digital", "https://atlasagency.example/services", "Agency client portals"),
                SearchResult("Atlas Digital", "https://atlasagency.example/contact", "Same agency")]


class FakeFetcher:
    def __init__(self):
        self.home = parse_page(
            "https://atlasagency.example/",
            "<title>Atlas Digital Agency</title><body><p>Our agency is based in Texas.</p>"
            "<p>Our digital agency works with businesses.</p>"
            "<a href='/contact'>Contact</a></body>",
        )
        self.contact = parse_page(
            "https://atlasagency.example/contact",
            "<body>Contact our team at <a href='mailto:hello@atlasagency.example'>Email</a></body>",
        )
        self.services = parse_page(
            "https://atlasagency.example/services",
            "<body><p>Our digital agency builds client portals for businesses.</p></body>",
        )

    def fetch(self, url):
        return {self.home.url: self.home, self.contact.url: self.contact,
                self.services.url: self.services}[url]


class DiscoveryTests(unittest.TestCase):
    def test_one_evidenced_contact_creates_one_review_card(self):
        database = FakeDatabase()
        result = DiscoveryRunner(database, FakeSearch(), fetcher=FakeFetcher()).run(limit=5)
        self.assertEqual(len(result.cards), 1)
        self.assertEqual(len(database.created), 1)
        self.assertEqual(len(database.messages), 1)
        self.assertEqual(database.created[0]["email_verified"], False)
        self.assertEqual(database.created[0]["verification_result"], "mx_unchecked")
        self.assertEqual(database.messages[0]["evidence"]["contact_source_url"], "https://atlasagency.example/contact")
        self.assertEqual(database.messages[0]["evidence"]["observation_source_url"], "https://atlasagency.example/services")
        self.assertIn("Exact body:", result.cards[0]["card_text"])

    def test_missing_sender_details_create_no_approvable_message(self):
        database = FakeDatabase(sender=False)
        result = DiscoveryRunner(database, FakeSearch(), fetcher=FakeFetcher()).run(limit=5)
        self.assertEqual(result.cards, [])
        self.assertEqual(database.messages, [])
        self.assertTrue(any("Sender postal address" in line for line in result.diagnostics))

    def test_missing_published_contact_is_kept_for_further_research(self):
        database = FakeDatabase()
        fetcher = FakeFetcher()
        fetcher.contact = parse_page(fetcher.contact.url, "<body>Contact our agency team</body>")
        result = DiscoveryRunner(database, FakeSearch(), fetcher=fetcher).run(limit=5)
        self.assertEqual(result.cards, [])
        self.assertEqual(database.messages, [])
        self.assertEqual(len(database.research_tasks), 1)
        self.assertEqual(database.research_tasks[0]["domain"], "atlasagency.example")
        self.assertIn("Published company-domain email not found", database.research_tasks[0]["reason"])

    def test_existing_contacted_company_is_never_recreated(self):
        database = FakeDatabase(existing={"id": "old-lead", "db_source": "hawkins", "status": "sent"})
        result = DiscoveryRunner(database, FakeSearch(), fetcher=FakeFetcher()).run(limit=5)
        self.assertEqual(result.cards, [])
        self.assertEqual(database.created, [])

    def test_legacy_www_domain_is_deduplicated(self):
        database = FakeDatabase()
        original_rows = database.rows
        def rows(table, filters, *, select="*"):
            if table == "cold_leads" and filters.get("company_domain") == "ilike.www.atlasagency.example":
                return [{"id": "old-lead", "db_source": "hawkins", "status": "sent"}]
            return original_rows(table, filters, select=select)
        database.rows = rows
        result = DiscoveryRunner(database, FakeSearch(), fetcher=FakeFetcher()).run(limit=5)
        self.assertEqual(result.cards, [])
        self.assertEqual(database.created, [])

    def test_unbound_draft_is_returned_for_telegram_retry(self):
        database = FakeDatabase(existing={"id": "lead-1", "db_source": "client_finder_brave", "status": "enriched"})
        original_rows = database.rows
        def rows(table, filters, *, select="*"):
            if table == "client_finder_messages":
                return [{"id": "message-1", "status": "draft"}]
            return original_rows(table, filters, select=select)
        database.rows = rows
        with patch("client_finder.discovery.stored_card", return_value={"message_id": "message-1", "revision": 1, "kind": "initial", "card_text": "exact stored draft"}):
            result = DiscoveryRunner(database, FakeSearch(), fetcher=FakeFetcher()).run(limit=5)
        self.assertEqual(len(result.cards), 1)
        self.assertEqual(result.cards[0]["card_text"], "exact stored draft")
        self.assertEqual(database.created, [])

    def test_disabled_daily_discovery_makes_no_search_calls(self):
        database = FakeDatabase()
        database.settings["discovery_enabled"] = False
        search = FakeSearch()
        result = DiscoveryRunner(database, search, fetcher=FakeFetcher()).run()
        self.assertEqual(result.cards, [])
        self.assertEqual(search.count, 0)


if __name__ == "__main__":
    unittest.main()
