"""Static safety contracts for inactive n8n mail workflows.

These checks do not prove a live n8n import, Gmail credential, or mailbox poll.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def workflow(name: str) -> dict:
    return json.loads((ROOT / "workflows" / name).read_text())


def nodes_by_name(data: dict) -> dict:
    return {node["name"]: node for node in data["nodes"]}


class WorkflowGraphTests(unittest.TestCase):
    def test_mail_workflow_references_exist(self) -> None:
        for name in ("03_inbox_monitor.json", "04_followup_due.json"):
            with self.subTest(name=name):
                data = workflow(name)
                nodes = nodes_by_name(data)
                self.assertEqual(len(nodes), len(data["nodes"]))
                self.assertFalse(data["active"])
                self.assertEqual(data["settings"]["saveDataErrorExecution"], "none")
                self.assertEqual(data["settings"]["saveDataSuccessExecution"], "none")
                self.assertFalse(data["settings"]["saveManualExecutions"])
                self.assertFalse(data["settings"]["saveExecutionProgress"])
                for source, outputs in data["connections"].items():
                    self.assertIn(source, nodes)
                    for branches in outputs.values():
                        for branch in branches:
                            for edge in branch:
                                self.assertIn(edge["node"], nodes)
                for node in data["nodes"]:
                    for reference in re.findall(
                        r"\$\('([^']+)'\)", json.dumps(node["parameters"])
                    ):
                        self.assertIn(reference, nodes)

    def test_no_automatic_prospect_email(self) -> None:
        for name in ("03_inbox_monitor.json", "04_followup_due.json"):
            with self.subTest(name=name):
                data = workflow(name)
                self.assertFalse(
                    any(
                        node["type"] == "n8n-nodes-base.gmail"
                        and node["parameters"].get("operation") in {"send", "reply"}
                        for node in data["nodes"]
                    )
                )


class InboxMonitorContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = workflow("03_inbox_monitor.json")
        self.nodes = nodes_by_name(self.data)

    def test_polls_full_read_and_unread_mail_with_bounded_batch(self) -> None:
        gmail = self.nodes["Fetch Gmail Window"]
        self.assertEqual(gmail["parameters"]["operation"], "getAll")
        self.assertFalse(gmail["parameters"]["simple"])
        self.assertEqual(gmail["parameters"]["limit"], 251)
        self.assertEqual(gmail["parameters"]["filters"]["readStatus"], "both")
        self.assertFalse(gmail["parameters"]["filters"]["includeSpamTrash"])
        self.assertIn("-in:sent", gmail["parameters"]["filters"]["q"])
        self.assertIn("-in:drafts", gmail["parameters"]["filters"]["q"])
        self.assertEqual(gmail["onError"], "continueErrorOutput")
        self.assertTrue(gmail["alwaysOutputData"])

    def test_personal_identity_is_checked_before_mail_read(self) -> None:
        guard=self.nodes['Personal Mailbox Verified?']
        self.assertIn('armageddonvivas@gmail.com',json.dumps(guard))
        self.assertEqual(self.nodes['Verify Personal Mailbox']['credentials'],self.nodes['Fetch Gmail Window']['credentials'])
        self.assertEqual(self.data['connections']['Poll Window Valid?']['main'][0][0]['node'],'Verify Personal Mailbox')
        self.assertEqual(self.data['connections']['Personal Mailbox Verified?']['main'][0][0]['node'],'Fetch Gmail Window')

    def test_checkpoint_is_read_and_advanced_only_by_service(self) -> None:
        load = self.nodes["Load Durable Mail Checkpoint"]
        self.assertIn("client_finder_mail_monitor_state", load["parameters"]["url"])
        window = self.nodes["Prepare One-Hour Poll Window"]["parameters"]
        text = json.dumps(window)
        self.assertIn("scanned_through", text)
        self.assertIn("10 * 60 * 1000", text)
        self.assertIn("60 * 60 * 1000", text)
        process = self.nodes["Process and Checkpoint Mail Poll"]
        self.assertEqual(process["parameters"]["url"], "http://client-finder:8088/mail-poll")
        self.assertIn("gmail_messages", process["parameters"]["jsonBody"])
        self.assertIn("scanned_since", process["parameters"]["jsonBody"])
        self.assertIn("scanned_until", process["parameters"]["jsonBody"])
        self.assertIn("Object.keys($json.gmail_messages[0]).length === 0", process["parameters"]["jsonBody"])
        self.assertNotIn(".filter(", process["parameters"]["jsonBody"])
        self.assertEqual(process["onError"], "continueErrorOutput")
        batch_guard = json.dumps(self.nodes["Batch At Most 250?"])
        self.assertIn("$json.gmail_messages.length <= 250", batch_guard)
        self.assertNotIn(".filter(", batch_guard)
        self.assertIn("$json.status === 'complete'", json.dumps(self.nodes["Poll Completed?"]))

    def test_failures_and_ambiguous_mail_alert_owner(self) -> None:
        connections = self.data["connections"]
        for name in (
            "Load Durable Mail Checkpoint",
            "Fetch Gmail Window",
            "Process and Checkpoint Mail Poll",
        ):
            self.assertEqual(
                connections[name]["main"][1][0]["node"],
                "Alert: Mail Monitor Failed",
            )
        self.assertEqual(
            connections["Poll Completed?"]["main"][1][0]["node"],
            "Alert: Mail Needs Checking",
        )
        self.assertEqual(
            connections["Alert: Mail Needs Checking"]["main"][0][0]["node"],
            "Stop: Mail Needs Checking",
        )
        self.assertEqual(
            connections["Alert: Mail Monitor Failed"]["main"][0][0]["node"],
            "Stop: Mail Poll Failed",
        )
        alert = self.nodes["Alert: Mail Needs Checking"]["parameters"]["text"]
        self.assertIn("gmail_id", alert)
        self.assertIn("reason", alert)
        self.assertNotIn("body", alert)
        self.assertEqual(self.data["settings"]["saveDataErrorExecution"], "none")
        self.assertEqual(self.data["settings"]["saveDataSuccessExecution"], "none")

    def test_stalled_send_sweep_is_independent_and_owner_visible(self) -> None:
        connections = self.data["connections"]
        self.assertEqual(
            connections["Every 5 Minutes: Stale Sends"]["main"][0][0]["node"],
            "Stale Sweep Configuration",
        )
        sweep = self.nodes["Mark Stale Send Attempts"]
        self.assertIn("client_finder_mark_stale_attempts", sweep["parameters"]["url"])
        self.assertEqual(sweep["onError"], "continueErrorOutput")
        self.assertEqual(
            connections["Stale Sweep Count Valid?"]["main"][1][0]["node"],
            "Alert: Stale Sweep Failed",
        )
        self.assertEqual(
            connections["Any Stale Attempts?"]["main"][0][0]["node"],
            "Alert: Uncertain Gmail Send",
        )
        self.assertIn(
            "No automatic resend",
            self.nodes["Alert: Uncertain Gmail Send"]["parameters"]["text"],
        )


class FollowUpContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data = workflow("04_followup_due.json")
        self.nodes = nodes_by_name(self.data)

    def test_service_only_prepares_drafts_and_posts_complete_card(self) -> None:
        service = self.nodes["Prepare Due Follow-ups"]
        self.assertEqual(
            service["parameters"]["url"],
            "http://client-finder:8088/followups/due",
        )
        self.assertEqual(service["parameters"]["jsonBody"], '{"limit":5}')
        card_guard = json.dumps(self.nodes["Stored Follow-up Card Complete?"])
        for required in ("message_id", "revision", "kind === 'followup'", "card_text", "<= 4096", "<= 64"):
            self.assertIn(required, card_guard)
        telegram = self.nodes["Post Exact Follow-up Card"]
        self.assertEqual(
            telegram["credentials"]["telegramApi"]["name"],
            "CLIENT_FINDER_TELEGRAM_BOT",
        )
        buttons = json.dumps(telegram["parameters"]["inlineKeyboard"])
        for action in ("approve", "edit", "skip", "dnc"):
            self.assertIn("cf:" + action + ":", buttons)
        bind = self.nodes["Bind Follow-up Card in Supabase"]
        self.assertIn("client_finder_bind_card", bind["parameters"]["url"])
        self.assertIn("card_id", bind["parameters"]["jsonBody"])
        self.assertEqual(self.data["settings"]["timezone"], "Asia/Manila")

    def test_service_and_bind_failures_alert_owner(self) -> None:
        connections = self.data["connections"]
        for node in (
            "Prepare Due Follow-ups",
            "Post Exact Follow-up Card",
            "Bind Follow-up Card in Supabase",
        ):
            self.assertEqual(self.nodes[node]["onError"], "continueErrorOutput")
        self.assertEqual(
            connections["Prepare Due Follow-ups"]["main"][1][0]["node"],
            "Alert: Follow-up Service Failed",
        )
        self.assertEqual(
            connections["Bind Follow-up Card in Supabase"]["main"][1][0]["node"],
            "Alert: Follow-up Card Unbound",
        )
        self.assertEqual(
            connections["Post Exact Follow-up Card"]["main"][1][0]["node"],
            "Stop: Follow-up Telegram Failed",
        )

    def test_followup_diagnostics_alert_owner_without_dropping_valid_cards(self) -> None:
        connections = self.data["connections"]
        self.assertEqual(
            connections["Prepare Due Follow-ups"]["main"][0][0]["node"],
            "Follow-up Diagnostics?",
        )
        self.assertEqual(
            {edge["node"] for edge in connections["Follow-up Diagnostics?"]["main"][0]},
            {"Alert: Follow-up Research Needs Review", "One Item per Follow-up Card"},
        )
        self.assertEqual(
            connections["Follow-up Diagnostics?"]["main"][1][0]["node"],
            "One Item per Follow-up Card",
        )


if __name__ == "__main__":
    unittest.main()
