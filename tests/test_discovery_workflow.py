"""Structural safety checks for the inactive daily discovery workflow."""

from __future__ import annotations

import json
import re
import unittest
from html import unescape
from pathlib import Path


WORKFLOW = Path(__file__).resolve().parents[1] / "workflows" / "01_agency_daily_discovery.json"


class DiscoveryWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = json.loads(WORKFLOW.read_text())
        cls.nodes = {node["name"]: node for node in cls.workflow["nodes"]}

    def destinations(self, name: str, output: int = 0) -> list[str]:
        return [edge["node"] for edge in self.workflow["connections"][name]["main"][output]]

    def assert_owner_alert_then_stop(self, source: str, alert: str, stop: str, output: int = 1) -> None:
        self.assertEqual(self.destinations(source, output), [alert])
        self.assertEqual(self.destinations(alert), [stop])
        self.assertEqual(self.destinations(alert, 1), [stop])
        self.assertEqual(self.nodes[alert]["onError"], "continueErrorOutput")
        self.assertEqual(self.nodes[alert]["credentials"]["telegramApi"]["name"], "CLIENT_FINDER_TELEGRAM_BOT")
        self.assertNotIn("$json", self.nodes[alert]["parameters"]["text"])
        self.assertEqual(self.nodes[stop]["type"], "n8n-nodes-base.stopAndError")

    def test_import_structure_and_inactive_schedule(self) -> None:
        workflow = self.workflow
        self.assertEqual(workflow["id"], "cfAgencyDailyDiscovery01")
        self.assertIs(workflow["active"], False)
        self.assertEqual(workflow["settings"]["timezone"], "Asia/Manila")
        self.assertEqual(workflow["settings"]["saveDataErrorExecution"], "none")
        self.assertEqual(workflow["settings"]["saveDataSuccessExecution"], "none")
        self.assertIs(workflow["settings"]["saveManualExecutions"], False)
        self.assertIs(workflow["settings"]["saveExecutionProgress"], False)
        self.assertEqual(len(self.nodes), len(workflow["nodes"]))
        self.assertEqual(len({node["id"] for node in workflow["nodes"]}), len(workflow["nodes"]))

        schedule = self.nodes["Daily 08:00 Manila"]
        self.assertEqual(schedule["type"], "n8n-nodes-base.scheduleTrigger")
        self.assertEqual(schedule["parameters"]["rule"]["interval"][0]["expression"], "0 8 * * *")
        self.assertEqual(self.nodes["Run Manually"]["type"], "n8n-nodes-base.manualTrigger")
        for source, outputs in workflow["connections"].items():
            self.assertIn(source, self.nodes)
            for route in outputs.values():
                for branch in route:
                    for edge in branch:
                        self.assertIn(edge["node"], self.nodes)
                        self.assertEqual(edge["type"], "main")
                        self.assertEqual(edge["index"], 0)

    def test_internal_discovery_only_and_fail_closed_card_guard(self) -> None:
        request = self.nodes["Discover Agency Prospects"]
        self.assertEqual(request["type"], "n8n-nodes-base.httpRequest")
        self.assertEqual(request["parameters"]["method"], "POST")
        self.assertEqual(request["parameters"]["url"], "http://client-finder:8088/discover")
        self.assertEqual(request["parameters"]["genericAuthType"], "httpBearerAuth")
        self.assertEqual(request["credentials"]["httpBearerAuth"]["name"], "CLIENT_FINDER_SERVICE_AUTH")
        self.assertEqual(json.loads(request["parameters"]["jsonBody"]), {"limit": 5})
        self.assertEqual(request["onError"], "continueErrorOutput")
        self.assertEqual(self.workflow["connections"]["Discover Agency Prospects"]["main"][1][0]["node"], "Tell Owner Discovery Service Failed")
        self.assertEqual(self.workflow["connections"]["Discover Agency Prospects"]["main"][0][0]["node"], "Discovery Result Valid?")
        self.assert_owner_alert_then_stop("Discovery Result Valid?", "Tell Owner Discovery Result Malformed", "Discovery Result Malformed")
        self.assertEqual(self.workflow["connections"]["Any Approval-Ready Cards?"]["main"][1][0]["node"], "Tell Owner No Ready Cards")
        no_cards = self.nodes["Tell Owner No Ready Cards"]["parameters"]["text"]
        self.assertIn("No approval-ready", no_cards)
        self.assertIn("diagnostics.slice(0,3)", no_cards)
        self.assertEqual(
            self.nodes["One Item per Review Card"]["parameters"]["fieldToSplitOut"], "cards"
        )
        guard = self.nodes["Stored Card Complete?"]["parameters"]["conditions"]["conditions"][0][
            "leftValue"
        ]
        for field in ("message_id", "revision", "card_text"):
            self.assertIn(field, guard)
        self.assertIn("['initial','followup'].includes($json.kind)", guard)
        self.assertIn("[0-9a-fA-F]{8}", guard)
        self.assertIn("[1-9][0-9]*", guard)
        self.assertIn("4096", guard)
        self.assertIn("64", guard)
        self.assert_owner_alert_then_stop("Stored Card Complete?", "Tell Owner Review Card Incomplete", "Incomplete Card")

    def test_partial_research_diagnostics_reach_owner_without_blocking_cards(self) -> None:
        self.assertEqual(self.destinations("Any Approval-Ready Cards?"), ["Partial Discovery Issues?"])
        self.assertEqual(self.destinations("Any Approval-Ready Cards?", 1), ["Tell Owner No Ready Cards"])
        condition = self.nodes["Partial Discovery Issues?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        self.assertIn("$json.diagnostics.length > 0", condition)
        self.assertEqual(
            self.destinations("Partial Discovery Issues?"),
            ["Tell Owner Partial Discovery Issues", "One Item per Review Card"],
        )
        self.assertEqual(self.destinations("Partial Discovery Issues?", 1), ["One Item per Review Card"])
        alert = self.nodes["Tell Owner Partial Discovery Issues"]
        self.assertEqual(alert["credentials"]["telegramApi"]["name"], "CLIENT_FINDER_TELEGRAM_BOT")
        self.assertEqual(alert["onError"], "continueErrorOutput")
        self.assertIn("$json.diagnostics.slice(0,3)", alert["parameters"]["text"])
        self.assertIn("&amp;", alert["parameters"]["text"])
        self.assertNotIn("Tell Owner Partial Discovery Issues", self.workflow["connections"])

    def test_telegram_card_and_bind_keep_owner_ids_unconfigured(self) -> None:
        telegram = self.nodes["Post Exact Review Card"]
        self.assertEqual(telegram["credentials"]["telegramApi"]["name"], "CLIENT_FINDER_TELEGRAM_BOT")
        parameters = telegram["parameters"]
        self.assertEqual(parameters["operation"], "sendMessage")
        self.assertEqual(parameters["replyMarkup"], "inlineKeyboard")
        self.assertIn("$json.card_text", parameters["text"])
        self.assertIn("&amp;", parameters["text"])
        self.assertEqual(parameters["additionalFields"]["parse_mode"], "HTML")
        self.assertIs(parameters["additionalFields"]["appendAttribution"], False)
        self.assertEqual(telegram["onError"], "continueErrorOutput")
        self.assert_owner_alert_then_stop("Post Exact Review Card", "Tell Owner Review Card Delivery Failed", "Telegram Card Delivery Failed")
        self.assert_owner_alert_then_stop("Telegram Card ID Returned?", "Tell Owner Telegram Card ID Uncertain", "Telegram Result Needs Checking")
        self.assertIn("independent n8n error workflow", self.nodes["Owner Configuration"]["notes"])
        example = 'Agency & Co <needs> "a full draft"\nSend as written.'
        escaped = example.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        self.assertEqual(unescape(escaped), example)

        buttons = [
            button
            for row in parameters["inlineKeyboard"]["rows"]
            for button in row["row"]["buttons"]
        ]
        self.assertEqual(
            [button["text"] for button in buttons],
            ["Approve & send", "Edit", "Skip", "Do not contact"],
        )
        for action, button in zip(("approve", "edit", "skip", "dnc"), buttons):
            callback = button["additionalFields"]["callback_data"]
            self.assertIn(f"cf:{action}:", callback)
            self.assertIn("$json.message_id", callback)
            self.assertIn("$json.revision", callback)
            self.assertLessEqual(len((f"cf:{action}:" + "a" * 36 + ":" + "9" * 10).encode()), 64)

        bind = self.nodes["Bind Telegram Card in Supabase"]
        self.assertEqual(bind["parameters"]["method"], "POST")
        self.assertIn("/rest/v1/rpc/client_finder_bind_card", bind["parameters"]["url"])
        self.assertEqual(bind["parameters"]["genericAuthType"], "httpCustomAuth")
        self.assertEqual(bind["onError"], "continueErrorOutput")
        self.assertEqual(self.workflow["connections"]["Bind Telegram Card in Supabase"]["main"][1][0]["node"], "Tell Owner Card Binding Failed")
        self.assertEqual(
            bind["credentials"]["httpCustomAuth"]["name"], "CLIENT_FINDER_SUPABASE_REST_AUTH"
        )
        for key in ("message_id:", "revision:", "owner_user_id:", "chat_id:", "card_id:"):
            self.assertIn(key, bind["parameters"]["jsonBody"])
        for credential in (request for node in self.workflow["nodes"] for request in node.get("credentials", {}).values()):
            self.assertNotIn("id", credential)

        config = self.nodes["Owner Configuration"]["parameters"]["assignments"]["assignments"]
        self.assertEqual(len(config), 3)
        self.assertEqual(
            {field["name"]: field["value"] for field in config},
            {
                "owner_user_id": "YOUR_CLIENT_FINDER_TELEGRAM_USER_ID",
                "chat_id": "YOUR_CLIENT_FINDER_TELEGRAM_PRIVATE_CHAT_ID",
                "supabase_base_url": "https://mtdavgadkiiofwikzdtn.supabase.co",
            },
        )
        serialized = WORKFLOW.read_text()
        for export in WORKFLOW.parent.glob("*.json"):
            data = json.loads(export.read_text())
            self.assertIs(data["active"], False, export.name)
            for node in data["nodes"]:
                assignments = node.get("parameters", {}).get("assignments", {}).get("assignments", [])
                for field in assignments:
                    if field.get("name") == "supabase_base_url":
                        self.assertEqual(field["value"], "https://mtdavgadkiiofwikzdtn.supabase.co", export.name)
        self.assertNotIn("HopperTheHeroBot", serialized)
        self.assertNotRegex(serialized, re.compile(r"eyJ[A-Za-z0-9_-]{50,}"))
        self.assertFalse(any(node["type"] in {"n8n-nodes-base.gmail", "n8n-nodes-base.code"} for node in self.workflow["nodes"]))


if __name__ == "__main__":
    unittest.main()
