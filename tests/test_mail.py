import base64
import unittest

from client_finder.mail import MailMonitor


def gmail_message(*, mid="in-1", thread="thread-1", sender="Agency <hello@agency.com>", subject="Re: idea", body="Thanks, not now."):
    encoded = base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")
    return {
        "id": mid, "threadId": thread, "internalDate": "1790445600000", "labelIds": ["INBOX"],
        "payload": {"mimeType": "text/plain", "headers": [
            {"name": "From", "value": sender}, {"name": "Subject", "value": subject},
            {"name": "To", "value": "sender@example.com"},
        ], "body": {"data": encoded}},
    }


class FakeDatabase:
    def __init__(self):
        self.calls = []
        self.messages = [{
            "id": "out-1", "lead_id": "lead-1", "recipient_email": "hello@agency.com",
            "gmail_message_id": "sent-1", "gmail_thread_id": "thread-1", "sent_at": "2026-09-26T00:00:00+00:00",
        }]

    def rows(self, table, filters, **kwargs):
        assert table == "client_finder_messages"
        return self.messages if filters["gmail_thread_id"] == "eq.thread-1" else []

    def rpc(self, name, values):
        self.calls.append((name, values))
        if name == "client_finder_record_mail_event":
            return True
        if name == "client_finder_record_mail_poll":
            return {"last_success_at": "2026-09-27T00:00:00+00:00"}
        if name == "client_finder_pause_sending":
            return {"sending_enabled": False}
        raise AssertionError(name)


class MailMonitorTests(unittest.TestCase):
    def test_matching_reply_records_event_before_checkpoint(self):
        db = FakeDatabase()
        result = MailMonitor(db).poll([gmail_message()], "2026-09-26T00:00:00Z", "2026-09-27T00:00:00Z")
        self.assertEqual(result["status"], "complete")
        self.assertEqual([name for name, _ in db.calls], ["client_finder_record_mail_event", "client_finder_record_mail_poll"])
        self.assertEqual(db.calls[0][1]["event_type"], "reply")
        self.assertEqual(db.calls[0][1]["original_gmail_message_id"], "sent-1")

    def test_optout_must_be_in_new_text(self):
        db = FakeDatabase()
        message = gmail_message(body="Thanks.\nOn Mon, Sep 26, 2026 someone wrote:\n> Please remove me from your list")
        MailMonitor(db).inspect(message)
        self.assertEqual(db.calls[0][1]["event_type"], "reply")
        db.calls.clear()
        MailMonitor(db).inspect(gmail_message(mid="in-2", body="Please remove me from your list."))
        self.assertEqual(db.calls[0][1]["event_type"], "optout")
        db.calls.clear()
        MailMonitor(db).inspect(gmail_message(mid="in-3", body="stop"))
        self.assertEqual(db.calls[0][1]["event_type"], "optout")

    def test_html_only_optout_ignores_quoted_footer(self):
        db = FakeDatabase()
        message = gmail_message(mid="in-html", body="")
        message["payload"]["mimeType"] = "text/html"
        message["payload"]["body"]["data"] = base64.urlsafe_b64encode(
            b"<div>unsubscribe</div><blockquote>Earlier newsletter footer</blockquote>"
        ).decode().rstrip("=")
        MailMonitor(db).inspect(message)
        self.assertEqual(db.calls[0][1]["event_type"], "optout")

    def test_matching_dsn_requires_final_recipient(self):
        db = FakeDatabase()
        message = gmail_message(sender="Mail Delivery Subsystem <mailer-daemon@googlemail.com>",
                                subject="Delivery Status Notification", body="Final-Recipient: rfc822; hello@agency.com")
        MailMonitor(db).inspect(message)
        self.assertEqual(db.calls[0][1]["event_type"], "bounce")
        self.assertEqual(db.calls[0][1]["bounced_recipient_email"], "hello@agency.com")

    def test_unmatched_bounce_pauses_and_does_not_checkpoint(self):
        db = FakeDatabase()
        message = gmail_message(thread="unknown", sender="mailer-daemon@googlemail.com",
                                subject="Delivery Status Notification")
        result = MailMonitor(db).poll([message], "2026-09-26T00:00:00Z", "2026-09-27T00:00:00Z")
        self.assertEqual(result["status"], "needs_checking")
        self.assertEqual([name for name, _ in db.calls], ["client_finder_pause_sending"])

    def test_unrelated_message_does_not_change_contact(self):
        db = FakeDatabase()
        result = MailMonitor(db).poll([gmail_message(thread="unknown")],
                                      "2026-09-26T00:00:00Z", "2026-09-27T00:00:00Z")
        self.assertEqual(result["results"][0]["status"], "ignored")
        self.assertEqual([name for name, _ in db.calls], ["client_finder_record_mail_poll"])

    def test_different_sender_in_known_thread_pauses_before_checkpoint(self):
        db = FakeDatabase()
        result = MailMonitor(db).poll(
            [gmail_message(sender="Agency colleague <colleague@agency.com>")],
            "2026-09-26T00:00:00Z", "2026-09-27T00:00:00Z",
        )
        self.assertEqual(result["status"], "needs_checking")
        self.assertIn("Unexpected sender", result["reason"])
        self.assertEqual([name for name, _ in db.calls], ["client_finder_pause_sending"])

    def test_malformed_gmail_item_pauses_before_checkpoint(self):
        malformed = []
        missing_labels = gmail_message(mid="missing-labels")
        del missing_labels["labelIds"]
        malformed.append(missing_labels)
        null_labels = gmail_message(mid="null-labels")
        null_labels["labelIds"] = None
        malformed.append(null_labels)
        bad_headers = gmail_message(mid="bad-headers")
        bad_headers["payload"]["headers"].append(None)
        malformed.append(bad_headers)
        bad_mime = gmail_message(mid="bad-mime")
        bad_mime["payload"]["parts"] = [None]
        malformed.append(bad_mime)
        for message in malformed:
            with self.subTest(gmail_id=message["id"]):
                db = FakeDatabase()
                result = MailMonitor(db).poll([message], "2026-09-26T00:00:00Z", "2026-09-27T00:00:00Z")
                self.assertEqual(result["status"], "needs_checking")
                self.assertEqual(result["gmail_id"], message["id"])
                self.assertEqual([name for name, _ in db.calls], ["client_finder_pause_sending"])

    def test_malformed_second_item_never_checkpoints_partial_poll(self):
        db = FakeDatabase()
        invalid = gmail_message(mid="in-2")
        invalid["labelIds"] = None
        result = MailMonitor(db).poll([gmail_message(), invalid],
                                      "2026-09-26T00:00:00Z", "2026-09-27T00:00:00Z")
        self.assertEqual(result["status"], "needs_checking")
        self.assertEqual([name for name, _ in db.calls],
                         ["client_finder_record_mail_event", "client_finder_pause_sending"])


if __name__ == "__main__":
    unittest.main()
