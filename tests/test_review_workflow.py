"""Structural gates for the inactive Telegram approval and Gmail workflow."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "workflows" / "02_telegram_review.json"
DISCOVERY = ROOT / "workflows" / "01_agency_daily_discovery.json"


class ReviewWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.workflow = json.loads(REVIEW.read_text())
        cls.nodes = {node["name"]: node for node in cls.workflow["nodes"]}
        cls.connections = cls.workflow["connections"]

    def destinations(self, name: str, output: int = 0) -> list[str]:
        return [edge["node"] for edge in self.connections[name]["main"][output]]

    def assert_owner_alert_then_stop(self, source: str, alert: str, stop: str, output: int = 1) -> None:
        self.assertEqual(self.destinations(source, output), [alert])
        self.assertEqual(self.destinations(alert), [stop])
        self.assertEqual(self.destinations(alert, 1), [stop])
        self.assertEqual(self.nodes[alert]["onError"], "continueErrorOutput")
        self.assertEqual(self.nodes[alert]["credentials"]["telegramApi"]["name"], "CLIENT_FINDER_TELEGRAM_BOT")
        self.assertNotIn("$json", self.nodes[alert]["parameters"]["text"])
        self.assertEqual(self.nodes[stop]["type"], "n8n-nodes-base.stopAndError")

    def test_inactive_import_graph_and_single_dedicated_trigger(self) -> None:
        workflow = self.workflow
        self.assertEqual(workflow["id"], "cfTelegramReviewSend01")
        self.assertIs(workflow["active"], False)
        self.assertEqual(workflow["settings"]["timezone"], "Asia/Manila")
        self.assertEqual(workflow["settings"]["saveDataErrorExecution"], "none")
        self.assertEqual(workflow["settings"]["saveDataSuccessExecution"], "none")
        self.assertIs(workflow["settings"]["saveManualExecutions"], False)
        self.assertIs(workflow["settings"]["saveExecutionProgress"], False)
        self.assertEqual(len(self.nodes), len(workflow["nodes"]))
        self.assertEqual(len({node["id"] for node in workflow["nodes"]}), len(workflow["nodes"]))
        triggers = [node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.telegramTrigger"]
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0]["parameters"]["updates"], ["callback_query", "message"])
        self.assertEqual(triggers[0]["credentials"]["telegramApi"]["name"], "CLIENT_FINDER_TELEGRAM_BOT")
        self.assertFalse(any(node["type"] == "n8n-nodes-base.code" for node in workflow["nodes"]))

        for name, channels in self.connections.items():
            self.assertIn(name, self.nodes)
            for route in channels.values():
                for branch in route:
                    for edge in branch:
                        self.assertIn(edge["node"], self.nodes)
                        self.assertEqual(edge["type"], "main")
                        self.assertEqual(edge["index"], 0)

    def test_owner_card_and_action_checked_before_any_rpc(self) -> None:
        guard = self.nodes["Owner and Callback Valid?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        for required in ("callback_query?.from?.id", "callback_query?.message?.chat?.id", "'private'", "message_id", "^cf:", "[0-9a-fA-F]{8}", "[0-9]{0,9}"):
            self.assertIn(required, guard)
        self.assertEqual(self.destinations("Owner and Callback Valid?"), ["Parsed Callback"])
        self.assert_owner_alert_then_stop("Owner and Callback Valid?", "Tell Owner Callback Rejected", "Unauthorized or Stale Callback")

        routes = self.connections["Review Action"]["main"]
        self.assertEqual(
            [branch[0]["node"] for branch in routes],
            ["Fetch Configured Sender", "Lock Card for Edit", "Skip Review Card", "Suppress Contact and Company"],
        )
        discovery = json.loads(DISCOVERY.read_text())
        card_node = next(node for node in discovery["nodes"] if node["name"] == "Post Exact Review Card")
        expected = [button["additionalFields"]["callback_data"] for row in card_node["parameters"]["inlineKeyboard"]["rows"] for button in row["row"]["buttons"]]
        revised_node = self.nodes["Post Revised Exact Card"]
        actual = [button["additionalFields"]["callback_data"] for row in revised_node["parameters"]["inlineKeyboard"]["rows"] for button in row["row"]["buttons"]]
        self.assertEqual(actual, expected)

    def test_callback_acknowledgment_cannot_block_saved_review_action(self) -> None:
        self.assertEqual(
            self.destinations("Parsed Callback"),
            ["Acknowledge Review Tap", "Review Action"],
        )
        self.assertEqual(self.destinations("Acknowledge Review Tap"), [])
        self.assertEqual(
            self.destinations("Acknowledge Review Tap", 1),
            ["Tell Owner Callback Acknowledgment Failed"],
        )
        self.assertEqual(self.nodes["Acknowledge Review Tap"]["onError"], "continueErrorOutput")
        alert = self.nodes["Tell Owner Callback Acknowledgment Failed"]
        self.assertEqual(alert["onError"], "continueErrorOutput")
        self.assertEqual(alert["credentials"]["telegramApi"]["name"], "CLIENT_FINDER_TELEGRAM_BOT")
        self.assertNotIn("Tell Owner Callback Acknowledgment Failed", self.connections)

    def test_sender_identity_is_verified_before_any_send_attempt_is_claimed(self) -> None:
        settings = self.nodes["Fetch Configured Sender"]
        self.assertEqual(settings["type"], "n8n-nodes-base.httpRequest")
        self.assertEqual(settings["parameters"]["method"], "GET")
        self.assertIn("/rest/v1/client_finder_settings?id=eq.1&select=sender_email", settings["parameters"]["url"])
        self.assertEqual(settings["parameters"]["genericAuthType"], "httpCustomAuth")
        self.assertEqual(settings["credentials"]["httpCustomAuth"]["name"], "CLIENT_FINDER_SUPABASE_REST_AUTH")
        self.assertEqual(settings["parameters"]["options"]["response"]["response"]["responseFormat"], "json")
        self.assertEqual(
            settings["parameters"]["headerParameters"]["parameters"],
            [{"name": "Accept", "value": "application/vnd.pgrst.object+json"}],
        )
        self.assertIs(settings["alwaysOutputData"], True)

        profile = self.nodes["Get Gmail Sender Profile"]
        send = self.nodes["Send Immutable Gmail Payload"]
        self.assertEqual(profile["type"], "n8n-nodes-base.httpRequest")
        self.assertEqual(profile["parameters"]["method"], "GET")
        self.assertEqual(profile["parameters"]["url"], "https://gmail.googleapis.com/gmail/v1/users/me/profile")
        self.assertEqual(profile["parameters"]["authentication"], "predefinedCredentialType")
        self.assertEqual(profile["parameters"]["nodeCredentialType"], "gmailOAuth2")
        self.assertEqual(profile["credentials"]["gmailOAuth2"], send["credentials"]["gmailOAuth2"])
        self.assertEqual(profile["parameters"]["options"]["response"]["response"]["responseFormat"], "json")
        self.assertIs(profile["alwaysOutputData"], True)

        configured_guard = self.nodes["Configured Sender Ready?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        self.assertIn("typeof $json.sender_email === 'string'", configured_guard)
        self.assertIn("$json.sender_email.trim()", configured_guard)
        match_guard = self.nodes["Gmail Sender Matches Configuration?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        for required in (
            "typeof $json.emailAddress === 'string'",
            "$json.emailAddress.trim().length > 0",
            "$('Fetch Configured Sender').first().json.sender_email",
            ".trim().toLowerCase() ===",
        ):
            self.assertIn(required, match_guard)

        self.assertEqual(self.destinations("Review Action"), ["Fetch Configured Sender"])
        self.assertEqual(self.destinations("Fetch Configured Sender"), ["Configured Sender Ready?"])
        self.assertEqual(self.destinations("Configured Sender Ready?"), ["Get Gmail Sender Profile"])
        self.assertEqual(self.destinations("Get Gmail Sender Profile"), ["Gmail Sender Matches Configuration?"])
        self.assertEqual(self.destinations("Gmail Sender Matches Configuration?"), ["Claim Approved Send"])
        for name in ("Fetch Configured Sender", "Get Gmail Sender Profile"):
            self.assertEqual(self.nodes[name]["onError"], "continueErrorOutput")
            self.assertIs(self.nodes[name]["retryOnFail"], False)
            self.assertNotIn("neverError", self.nodes[name]["parameters"]["options"]["response"]["response"])
        self.assert_owner_alert_then_stop("Fetch Configured Sender", "Tell Owner Sender Identity Failed", "Sender Identity Unverified")
        self.assert_owner_alert_then_stop("Configured Sender Ready?", "Tell Owner Sender Identity Failed", "Sender Identity Unverified")
        self.assert_owner_alert_then_stop("Get Gmail Sender Profile", "Tell Owner Sender Identity Failed", "Sender Identity Unverified")
        self.assert_owner_alert_then_stop("Gmail Sender Matches Configuration?", "Tell Owner Sender Identity Failed", "Sender Identity Unverified")

        inbound_to_claim = [
            source
            for source, routes in self.connections.items()
            for branch in routes["main"]
            for edge in branch
            if edge["node"] == "Claim Approved Send"
        ]
        self.assertEqual(inbound_to_claim, ["Gmail Sender Matches Configuration?"])

    def test_approval_uses_immutable_attempt_and_unknown_result_path(self) -> None:
        self.assertEqual(self.destinations("Claim Approved Send"), ["Recheck and Begin Send"])
        self.assertEqual(self.destinations("Claim Approved Send", 1), ["Tell Owner Approval Claim Uncertain"])
        self.assertEqual(self.destinations("Recheck and Begin Send"), ["Approved Attempt Still Sendable?"])
        self.assertEqual(self.destinations("Recheck and Begin Send", 1), ["Mark Gmail Result Needs Checking"])
        self.assertEqual(self.destinations("Approved Attempt Still Sendable?"), ["Send Immutable Gmail Payload"])
        self.assert_owner_alert_then_stop("Approved Attempt Still Sendable?", "Tell Owner Approved Send Stopped", "Send Stopped by Database")
        self.assertIs(self.nodes["Recheck and Begin Send"]["alwaysOutputData"], True)
        for node_name, rpc in (
            ("Claim Approved Send", "client_finder_claim_send"),
            ("Recheck and Begin Send", "client_finder_begin_send"),
            ("Record Confirmed Gmail Send", "client_finder_complete_send"),
            ("Mark Gmail Result Needs Checking", "client_finder_mark_send_unknown"),
        ):
            node = self.nodes[node_name]
            self.assertIn("/rpc/" + rpc, node["parameters"]["url"])
            self.assertEqual(node["parameters"]["genericAuthType"], "httpCustomAuth")
            self.assertEqual(
                node["parameters"]["headerParameters"]["parameters"][0],
                {"name": "Accept", "value": "application/vnd.pgrst.object+json"},
            )

        gmail = self.nodes["Send Immutable Gmail Payload"]
        self.assertEqual(gmail["type"], "n8n-nodes-base.gmail")
        self.assertEqual(gmail["credentials"]["gmailOAuth2"]["name"], "CLIENT_FINDER_GMAIL")
        self.assertEqual(gmail["parameters"]["sendTo"], "={{ $json.recipient_email }}")
        self.assertEqual(gmail["parameters"]["subject"], "={{ $json.subject }}")
        self.assertEqual(gmail["parameters"]["message"], "={{ $json.body }}")
        self.assertIs(gmail["parameters"]["options"]["appendAttribution"], False)
        self.assertEqual(gmail["parameters"]["operation"], "send")
        self.assertNotIn("threadId", gmail["parameters"])
        self.assertIn("follow-up", gmail["notes"])
        self.assertIs(gmail["retryOnFail"], False)
        self.assertEqual(gmail["onError"], "continueErrorOutput")
        self.assertEqual(self.destinations("Send Immutable Gmail Payload", 1), ["Mark Gmail Result Needs Checking"])
        self.assertEqual(self.destinations("Gmail IDs Returned?", 1), ["Mark Gmail Result Needs Checking"])
        self.assertEqual(self.destinations("Record Confirmed Gmail Send", 1), ["Mark Gmail Result Needs Checking", "Tell Owner Gmail IDs Need Recording"])
        recording_alert = self.nodes["Tell Owner Gmail IDs Need Recording"]["parameters"]["text"]
        self.assertIn("$('Gmail IDs Returned?').first().json.id", recording_alert)
        self.assertIn("$('Gmail IDs Returned?').first().json.threadId", recording_alert)
        self.assertEqual(self.destinations("Mark Gmail Result Needs Checking", 1), ["Tell Owner to Check Sent Mail"])
        for name in ("Claim Approved Send", "Recheck and Begin Send", "Record Confirmed Gmail Send", "Mark Gmail Result Needs Checking"):
            self.assertEqual(self.nodes[name]["onError"], "continueErrorOutput")
        self.assertIn("$('Claim Approved Send').first().json.id", self.nodes["Mark Gmail Result Needs Checking"]["parameters"]["jsonBody"])
        self.assertIn("gmail_message_id", self.nodes["Record Confirmed Gmail Send"]["parameters"]["jsonBody"])
        self.assertIn("gmail_thread_id", self.nodes["Record Confirmed Gmail Send"]["parameters"]["jsonBody"])

    def test_confirmed_send_requires_saved_matching_provider_ids(self) -> None:
        self.assertIs(self.nodes["Record Confirmed Gmail Send"]["alwaysOutputData"], True)
        self.assertEqual(
            self.destinations("Record Confirmed Gmail Send"),
            ["Confirmed Send Record Matches Gmail?"],
        )
        guard = self.nodes["Confirmed Send Record Matches Gmail?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        for required in (
            "$json.status === 'sent'",
            "$('Claim Approved Send').first().json.id",
            "$('Gmail IDs Returned?').first().json.id",
            "$('Gmail IDs Returned?').first().json.threadId",
            "$json.sent_at",
        ):
            self.assertIn(required, guard)
        self.assertEqual(self.destinations("Confirmed Send Record Matches Gmail?"), ["Tell Owner Gmail Accepted"])
        self.assertEqual(
            self.destinations("Confirmed Send Record Matches Gmail?", 1),
            ["Mark Gmail Result Needs Checking", "Tell Owner Gmail IDs Need Recording"],
        )

    def test_edit_reply_creates_new_card_and_rebinds_revision(self) -> None:
        self.assertIn("/rpc/client_finder_request_edit", self.nodes["Lock Card for Edit"]["parameters"]["url"])
        owner_guard = self.nodes["Owner Reply to Review Card?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        self.assertIn("message?.from?.id", owner_guard)
        self.assertIn("reply_to_message?.message_id", owner_guard)
        self.assertEqual(self.destinations("Owner Reply to Review Card?", 1), [])
        query = self.nodes["Find Pending Edit by Card"]["parameters"]["queryParameters"]["parameters"]
        self.assertEqual(next(item["value"] for item in query if item["name"] == "status"), "eq.edit_requested")
        self.assertIn("/rpc/client_finder_edit_message", self.nodes["Create New Message Revision"]["parameters"]["url"])
        self.assertEqual(self.nodes["Render Revised Exact Card"]["parameters"]["url"], "http://client-finder:8088/card")
        self.assertEqual(self.destinations("Revised Card Complete?"), ["Post Revised Exact Card"])
        revised_guard = self.nodes["Revised Card Complete?"]["parameters"]["conditions"]["conditions"][0]["leftValue"]
        self.assertIn("['initial','followup'].includes($json.kind)", revised_guard)
        self.assertIn("/rpc/client_finder_bind_card", self.nodes["Bind Revised Card"]["parameters"]["url"])
        for name in ("Lock Card for Edit", "Skip Review Card", "Suppress Contact and Company", "Find Pending Edit by Card", "Create New Message Revision", "Render Revised Exact Card"):
            self.assertEqual(self.nodes[name]["onError"], "continueErrorOutput")
            self.assertEqual(self.destinations(name, 1), ["Tell Owner Review Action Failed"])
        self.assert_owner_alert_then_stop("One Pending Edit Found?", "Tell Owner Edit Card Stale", "Edit Card Missing or Stale")
        self.assert_owner_alert_then_stop("Revised Card Complete?", "Tell Owner Revised Card Incomplete", "Revised Card Incomplete")
        self.assert_owner_alert_then_stop("Post Revised Exact Card", "Tell Owner Revised Card Delivery Failed", "Revised Telegram Delivery Failed")
        self.assert_owner_alert_then_stop("Revised Telegram ID Returned?", "Tell Owner Revised Telegram ID Uncertain", "Revised Telegram Result Needs Checking")
        self.assertIn("independent n8n error workflow", self.nodes["Owner Configuration"]["notes"])
        self.assertEqual(self.destinations("Bind Revised Card", 1), ["Tell Owner Revised Card Binding Failed"])
        self.assertIn("buttons cannot approve", self.nodes["Tell Owner Revised Card Binding Failed"]["parameters"]["text"])
        revised = self.nodes["Post Revised Exact Card"]["parameters"]
        self.assertEqual(revised["additionalFields"]["parse_mode"], "HTML")
        self.assertIs(revised["additionalFields"]["appendAttribution"], False)
        self.assertIn("$json.card_text", revised["text"])

    def test_no_embedded_secrets_or_existing_bot_reference(self) -> None:
        workflow_text = REVIEW.read_text()
        self.assertNotIn("HopperTheHeroBot", workflow_text)
        self.assertNotIn("@scalgent22312_bot", workflow_text)
        for node in self.workflow["nodes"]:
            for credential in node.get("credentials", {}).values():
                self.assertNotIn("id", credential)
                self.assertTrue(credential["name"].startswith("CLIENT_FINDER_"))
        config = self.nodes["Owner Configuration"]["parameters"]["assignments"]["assignments"]
        self.assertEqual(len(config), 3)
        self.assertEqual(
            {item["name"]: item["value"] for item in config},
            {
                "owner_user_id": "YOUR_CLIENT_FINDER_TELEGRAM_USER_ID",
                "chat_id": "YOUR_CLIENT_FINDER_TELEGRAM_PRIVATE_CHAT_ID",
                "supabase_base_url": "https://mtdavgadkiiofwikzdtn.supabase.co",
            },
        )


if __name__ == "__main__":
    unittest.main()
