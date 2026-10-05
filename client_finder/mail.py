"""Conservative Gmail inbox classification and Supabase event recording.

Only a confirmed outbound Gmail thread plus a matching sender (or DSN
recipient) can change contact state. Ambiguous delivery failures pause sends.
"""

from __future__ import annotations

import base64
import binascii
import re
from datetime import datetime, timezone
from email.utils import getaddresses
from html.parser import HTMLParser
from typing import Any

from .providers import ProviderError, SupabaseRest


class MailNeedsChecking(Exception):
    def __init__(self, gmail_id: str, reason: str) -> None:
        super().__init__(reason)
        self.gmail_id = gmail_id
        self.reason = reason


def _headers(message: dict[str, Any]) -> dict[str, str]:
    payload = message.get("payload")
    if not isinstance(payload, dict) or not isinstance(payload.get("headers"), list):
        raise MailNeedsChecking(str(message.get("id", "")), "Full Gmail headers are missing")
    headers: dict[str, str] = {}
    for item in payload["headers"]:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not isinstance(item.get("value"), str):
            raise MailNeedsChecking(str(message.get("id", "")), "Gmail headers are malformed")
        name = item["name"].lower()
        if name in ("from", "to", "subject") and name in headers:
            raise MailNeedsChecking(str(message.get("id", "")), "Gmail identity headers are duplicated")
        headers[name] = item["value"]
    if any(name not in headers for name in ("from", "to", "subject")):
        raise MailNeedsChecking(str(message.get("id", "")), "Gmail identity headers are missing")
    return headers


def _validate_mime(part: dict[str, Any], gmail_id: str, *, depth: int = 0) -> None:
    if depth > 12:
        raise MailNeedsChecking(gmail_id, "Gmail MIME nesting needs review")
    body = part.get("body")
    if body is not None and (not isinstance(body, dict) or ("data" in body and not isinstance(body["data"], str))):
        raise MailNeedsChecking(gmail_id, "Gmail MIME body is malformed")
    children = part.get("parts")
    if children is not None:
        if not isinstance(children, list):
            raise MailNeedsChecking(gmail_id, "Gmail MIME parts are malformed")
        for child in children:
            if not isinstance(child, dict):
                raise MailNeedsChecking(gmail_id, "Gmail MIME parts are malformed")
            _validate_mime(child, gmail_id, depth=depth + 1)


def _addresses(value: str) -> set[str]:
    return {email.lower() for _, email in getaddresses([value]) if "@" in email}


def _plain_parts(part: dict[str, Any], *, depth: int = 0) -> list[str]:
    if depth > 6:
        return []
    found: list[str] = []
    if part.get("mimeType") in ("text/plain", "message/delivery-status"):
        encoded = part.get("body", {}).get("data") if isinstance(part.get("body"), dict) else None
        if isinstance(encoded, str) and len(encoded) <= 100_000:
            try:
                raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                found.append(raw[:64_000].decode("utf-8", errors="replace"))
            except (ValueError, binascii.Error):
                pass
    for child in part.get("parts", []) if isinstance(part.get("parts"), list) else []:
        if isinstance(child, dict):
            found.extend(_plain_parts(child, depth=depth + 1))
    return found


class _HTMLReplyText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.quoted = False
        self.words: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in ("style", "script", "noscript"):
            self.hidden += 1
        if tag == "blockquote" or "gmail_quote" in str(values.get("class", "")):
            self.quoted = True
        if tag in ("br", "p", "div", "li"):
            self.words.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script", "noscript") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden and not self.quoted:
            self.words.append(data)


def _html_parts(part: dict[str, Any], *, depth: int = 0) -> list[str]:
    if depth > 6:
        return []
    found: list[str] = []
    if part.get("mimeType") == "text/html":
        encoded = part.get("body", {}).get("data") if isinstance(part.get("body"), dict) else None
        if isinstance(encoded, str) and len(encoded) <= 100_000:
            try:
                raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                parser = _HTMLReplyText()
                parser.feed(raw[:64_000].decode("utf-8", errors="replace"))
                found.append(" ".join(parser.words))
            except (ValueError, binascii.Error):
                pass
    for child in part.get("parts", []) if isinstance(part.get("parts"), list) else []:
        if isinstance(child, dict):
            found.extend(_html_parts(child, depth=depth + 1))
    return found


def _body(message: dict[str, Any]) -> str:
    payload = message.get("payload", {})
    if not isinstance(payload, dict):
        return ""
    plain = _plain_parts(payload)
    return "\n".join(plain if plain else _html_parts(payload))


def _top_reply(body: str) -> str:
    lines: list[str] = []
    for line in body.splitlines():
        if line.lstrip().startswith(">") or re.match(r"On .{8,160} wrote:\s*$", line, re.I):
            break
        lines.append(line)
        if sum(len(value) for value in lines) > 600:
            break
    return " ".join(lines)[:600].strip()


def _is_optout(text: str) -> bool:
    if text.strip().casefold().rstrip(".! ") in ("stop", "unsubscribe", "remove me", "opt out", "do not contact me"):
        return True
    return bool(re.search(
        r"\b(?:please\s+(?:remove\s+me|stop\s+(?:emailing|contacting)\s+me|unsubscribe\s+me)|"
        r"do\s+not\s+(?:email|contact)\s+me|unsubscribe\s+me|remove\s+me\s+from\s+(?:your\s+)?list)\b",
        text, re.I,
    ))


def _final_recipient(body: str) -> str:
    match = re.search(r"(?im)^Final-Recipient:\s*(?:rfc822;)?\s*([^\s;<>]+@[^\s;<>]+)", body)
    return match.group(1).lower() if match else ""


def _timestamp(message: dict[str, Any]) -> str:
    try:
        milliseconds = int(message["internalDate"])
        return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()
    except (KeyError, ValueError, TypeError, OverflowError) as exc:
        raise MailNeedsChecking(str(message.get("id", "")), "Gmail received time is missing") from exc


class MailMonitor:
    def __init__(self, database: SupabaseRest) -> None:
        self.database = database

    def inspect(self, message: dict[str, Any]) -> dict[str, str]:
        gmail_id = message.get("id")
        thread_id = message.get("threadId")
        if not isinstance(gmail_id, str) or not gmail_id or not isinstance(thread_id, str) or not thread_id:
            gmail_id = gmail_id if isinstance(gmail_id, str) else ""
            raise MailNeedsChecking(gmail_id, "Full Gmail message and thread IDs are required")
        labels = message.get("labelIds")
        if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
            raise MailNeedsChecking(gmail_id, "Gmail labels are missing or malformed")
        headers = _headers(message)
        _validate_mime(message["payload"], gmail_id)
        received_at = _timestamp(message)
        if "SENT" in labels:
            return {"status": "ignored", "gmail_id": gmail_id, "reason": "outbound_message"}
        from_addresses = _addresses(headers.get("from", ""))
        if len(from_addresses) != 1:
            raise MailNeedsChecking(gmail_id, "Inbound sender is ambiguous")
        sender = next(iter(from_addresses))
        subject = headers.get("subject", "")
        body = _body(message)
        bounce_like = (
            sender.split("@", 1)[0] in ("mailer-daemon", "postmaster")
            or bool(re.search(r"(?:delivery status notification|undelivered mail|delivery failure)", subject, re.I))
        )
        rows = self.database.rows("client_finder_messages", {
            "gmail_thread_id": f"eq.{thread_id}", "status": "in.(sent,send_unknown)"
        }, select="id,lead_id,recipient_email,gmail_message_id,gmail_thread_id,sent_at")
        if not rows:
            if bounce_like:
                raise MailNeedsChecking(gmail_id, "Delivery failure is outside a known Gmail thread")
            return {"status": "ignored", "gmail_id": gmail_id, "reason": "unrelated_thread"}
        recipients = {str(row["recipient_email"]).lower() for row in rows}
        if len(recipients) != 1:
            raise MailNeedsChecking(gmail_id, "Gmail thread maps to multiple recipients")
        rows.sort(key=lambda row: str(row.get("sent_at") or ""), reverse=True)
        original = rows[0]
        if not original.get("gmail_message_id"):
            raise MailNeedsChecking(gmail_id, "Outbound Gmail result is unresolved")
        recipient = next(iter(recipients))
        if bounce_like:
            bounced_recipient = _final_recipient(body)
            if bounced_recipient != recipient:
                raise MailNeedsChecking(gmail_id, "Delivery failure lacks a matching Final-Recipient")
            event_type = "bounce"
        elif sender == recipient:
            if not body.strip():
                raise MailNeedsChecking(gmail_id, "Reply body is unavailable for opt-out review")
            bounced_recipient = ""
            event_type = "optout" if _is_optout(_top_reply(body)) else "reply"
        else:
            # A colleague can reply in the same conversation. We cannot safely
            # attribute that reply or an opt-out to the original recipient, but
            # silently ignoring it could leave an approved follow-up eligible.
            raise MailNeedsChecking(gmail_id, "Unexpected sender in a known Gmail thread")
        accepted = self.database.rpc("client_finder_record_mail_event", {
            "provider_event_id": gmail_id,
            "message_id": original["id"], "event_type": event_type,
            "occurred_at": received_at,
            "gmail_thread_id": thread_id,
            "original_gmail_message_id": original["gmail_message_id"],
            "sender_email": sender,
            "bounced_recipient_email": bounced_recipient or None,
            "event_note": "Gmail inbox monitor",
        })
        if not isinstance(accepted, bool):
            raise ProviderError("Mail event was not acknowledged")
        return {"status": "recorded" if accepted else "duplicate", "gmail_id": gmail_id, "reason": event_type}

    def poll(self, gmail_messages: list[dict[str, Any]], scanned_since: str, scanned_until: str) -> dict[str, Any]:
        results: list[dict[str, str]] = []
        try:
            if not isinstance(gmail_messages, list) or len(gmail_messages) > 250:
                raise ValueError("Mailbox batch must contain at most 250 messages")
            try:
                since = datetime.fromisoformat(scanned_since.replace("Z", "+00:00"))
                until = datetime.fromisoformat(scanned_until.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("Mailbox interval requires ISO timestamps") from exc
            if since.tzinfo is None or until.tzinfo is None or since >= until:
                raise ValueError("Mailbox interval is invalid")
            for message in gmail_messages:
                if not isinstance(message, dict):
                    raise ValueError("Gmail message must be an object")
                try:
                    results.append(self.inspect(message))
                except MailNeedsChecking as exc:
                    self.database.rpc("client_finder_pause_sending", {"reason": f"Gmail {exc.gmail_id}: {exc.reason}"[:240]})
                    results.append({"status": "needs_checking", "gmail_id": exc.gmail_id, "reason": exc.reason})
                    return {"status": "needs_checking", "gmail_id": exc.gmail_id, "reason": exc.reason, "results": results}
            checkpoint = self.database.rpc("client_finder_record_mail_poll", {
                "scanned_since": scanned_since, "scanned_until": scanned_until,
                "fetched_count": len(gmail_messages),
            })
            if not isinstance(checkpoint, dict) or not checkpoint.get("last_success_at"):
                raise ProviderError("Mailbox checkpoint was not confirmed")
        except Exception:
            try:
                self.database.rpc("client_finder_pause_sending", {"reason": "Gmail inbox poll failed before checkpoint"})
            except Exception:
                pass
            raise
        return {"status": "complete", "results": results, "checkpoint": checkpoint}
