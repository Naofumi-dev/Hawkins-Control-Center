import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from client_finder.followups import _due_after_five_weekdays, prepare_due_followups


class FakeDatabase:
    def __init__(self, configured=True, existing=None, parents=None):
        self.configured = configured
        self.existing = [existing] if isinstance(existing, dict) else (existing or [])
        self.parents = parents if parents is not None else [{
            "id": "parent-1", "lead_id": "lead-1", "deliverable_id": "proposal_preparation",
            "sent_at": "2020-01-01T00:00:00Z",
        }]
        self.rpc_calls = []
        self.pages = []

    def rows(self, table, filters, **kwargs):
        if table == "client_finder_settings":
            return [{"sender_name": "A Vivas", "postal_address": "Business mailing address",
                     "commercial_label": "Business inquiry", "opt_out_route": "Reply stop"}] if self.configured else [{}]
        if table == "client_finder_messages" and filters.get("kind") == "eq.initial":
            offset = int(filters["offset"])
            self.pages.append(offset)
            return self.parents[offset:offset + int(filters["limit"])]
        if table == "client_finder_messages":
            parent_ids = set(filters["parent_message_id"][4:-1].split(","))
            return [row for row in self.existing if row.get("parent_message_id", "parent-1") in parent_ids]
        if table == "client_finder_deliverables":
            return [] if filters["id"] == "eq.missing" else [{"scope_text": "a reviewable proposal draft system"}]
        if table == "cold_leads":
            return [{"company_name": "Agency One"}]
        raise AssertionError(table)

    def rpc(self, name, values):
        self.rpc_calls.append((name, values))
        return {"id": "followup-1"}


class FollowupTests(unittest.TestCase):
    def test_prepares_unsent_new_subject_and_uses_due_rpc(self):
        db = FakeDatabase()
        with patch("client_finder.followups.stored_card", return_value={"message_id": "followup-1", "revision": 1, "kind": "followup", "card_text": "full card"}):
            result = prepare_due_followups(db)
        self.assertEqual(len(result["cards"]), 1)
        self.assertTrue(result["cards"][0]["ready_for_approval"])
        name, values = db.rpc_calls[0]
        self.assertEqual(name, "client_finder_create_due_followup")
        self.assertTrue(values["subject"].startswith("Checking back"))
        self.assertNotIn("Re:", values["subject"])
        self.assertIn("Reply stop", values["body"])
        self.assertEqual(result["status"], "complete")

    def test_missing_sender_details_creates_nothing(self):
        db = FakeDatabase(configured=False)
        result = prepare_due_followups(db)
        self.assertEqual(result["cards"], [])
        self.assertEqual(db.rpc_calls, [])
        self.assertEqual(result["status"], "needs_attention")
        self.assertEqual(result["diagnostic_count"], 1)

    def test_existing_unbound_followup_is_posted_again_without_new_draft(self):
        db = FakeDatabase(existing={"id": "followup-1", "status": "draft", "parent_message_id": "parent-1"})
        with patch("client_finder.followups.stored_card", return_value={"message_id": "followup-1", "revision": 1, "kind": "followup", "card_text": "exact stored draft"}):
            result = prepare_due_followups(db)
        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(db.rpc_calls, [])

    def test_scans_past_first_100_parents_without_starving_newer_due_send(self):
        parents = [{"id": f"parent-{n}", "lead_id": "lead-1",
                    "deliverable_id": "proposal_preparation", "sent_at": "2020-01-01T00:00:00Z"}
                   for n in range(101)]
        existing = [{"id": f"followup-{n}", "status": "sent", "parent_message_id": f"parent-{n}"}
                    for n in range(100)]
        db = FakeDatabase(existing=existing, parents=parents)
        with patch("client_finder.followups.stored_card", return_value={"message_id": "followup-new", "revision": 1,
                                                                 "kind": "followup", "card_text": "full card"}):
            result = prepare_due_followups(db)
        self.assertEqual(db.pages, [0, 100])
        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(db.rpc_calls[0][1]["initial_message_id"], "parent-100")

    def test_diagnostics_are_visible_alongside_valid_cards(self):
        parents = [
            {"id": "parent-bad", "lead_id": "lead-1", "deliverable_id": "missing", "sent_at": "2020-01-01T00:00:00Z"},
            {"id": "parent-good", "lead_id": "lead-1", "deliverable_id": "proposal_preparation", "sent_at": "2020-01-02T00:00:00Z"},
        ]
        db = FakeDatabase(parents=parents)
        with patch("client_finder.followups.stored_card", return_value={"message_id": "followup-1", "revision": 1,
                                                                 "kind": "followup", "card_text": "full card"}):
            result = prepare_due_followups(db)
        self.assertEqual(result["status"], "needs_attention")
        self.assertEqual(result["diagnostic_count"], 1)
        self.assertIn("parent-bad", result["diagnostics"][0])
        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(db.rpc_calls[0][1]["initial_message_id"], "parent-good")

    def test_five_weekdays_preserve_manila_send_time(self):
        sent_at = "2026-09-25T12:00:00Z"  # Friday, 20:00 Manila
        self.assertFalse(_due_after_five_weekdays(sent_at, datetime.fromisoformat("2026-10-02T19:59:59+08:00")))
        self.assertTrue(_due_after_five_weekdays(sent_at, datetime.fromisoformat("2026-10-02T20:00:00+08:00")))

    def test_recent_send_is_not_drafted_or_reported_as_an_error(self):
        recent = {"id": "parent-recent", "lead_id": "lead-1", "deliverable_id": "proposal_preparation",
                  "sent_at": datetime.now(timezone.utc).isoformat()}
        db = FakeDatabase(parents=[recent])
        result = prepare_due_followups(db)
        self.assertEqual(result, {"status": "complete", "cards": [], "diagnostics": [], "diagnostic_count": 0})
        self.assertEqual(db.rpc_calls, [])


if __name__ == "__main__":
    unittest.main()
