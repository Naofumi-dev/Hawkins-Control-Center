"""Mailbox normalization, conservative classification, and gap-free synchronization."""
from __future__ import annotations

import re
from datetime import datetime
from email.utils import getaddresses
from urllib.parse import urlparse

from .gmail import GmailError, OWNER_EMAIL
from .mail import _headers, _body, _top_reply, _is_optout, _timestamp, _validate_mime
from .providers import ProviderError

CATEGORIES = {"onlinejobs_conversation", "direct_client", "job_alert", "other", "needs_review"}
STAGES = {"new", "qualified", "loom_call", "proposal_offer", "won", "lost", "onboarding"}
INTENTS = {"loom_requested", "meeting_requested", "proposal_requested", "question", "reply", "optout", "bounce", "notification", "unknown"}
EMAIL_RE = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9-]+(?:\.[A-Z0-9-]+)+", re.I)


def business_email(value):
    if not isinstance(value, str) or len(value) > 254 or not EMAIL_RE.fullmatch(value):
        return False
    local, domain = value.lower().split("@")
    return not (domain == "onlinejobs.ph" or domain.endswith(".onlinejobs.ph") or
                local in {"noreply", "no-reply", "notifications", "mailer-daemon", "postmaster"} or
                value.lower() == OWNER_EMAIL)


def platform_reference(text):
    for match in re.findall(r"https://[^\s<>\"']+", text):
        url = urlparse(match.rstrip(".,)"))
        if (url.hostname in {"onlinejobs.ph", "www.onlinejobs.ph", "v2.onlinejobs.ph", "mail.onlinejobs.ph"}
                and re.search(r"/(?:message|messages|conversation|conversations|jobseekers/job)/", url.path, re.I)):
            return url._replace(fragment="").geturl()
    return ""


def classify(subject, body, sender, *, platform=False, outbound=False, known=False):
    top = _top_reply(body)
    text = (subject + "\n" + top).lower()
    intent = "unknown"
    evidence = []
    if _is_optout(top):
        intent = "optout"
    elif sender.split("@", 1)[0] in {"mailer-daemon", "postmaster"} or re.search(r"delivery status notification|undelivered mail", subject, re.I):
        intent = "bounce"
    elif re.search(r"\b(?:loom|video|demo|walkthrough)\b", text) and re.search(r"\b(?:send|email|share|yes|please|want|show)\b", text):
        intent = "loom_requested"
    elif re.search(r"\b(?:schedule|book|available|availability)\b.{0,45}\b(?:call|meeting|interview)\b", text):
        intent = "meeting_requested"
    elif re.search(r"\b(?:send|share|need|request)\b.{0,40}\b(?:proposal|quote|estimate)\b", text):
        intent = "proposal_requested"
    elif "?" in top:
        intent = "question"
    elif known:
        intent = "reply"
    if platform:
        alert = bool(re.search(r"job alert|new jobs? (?:for|matching)|recommended jobs|jobs you might", text))
        category = "job_alert" if alert else "onlinejobs_conversation"
        evidence.append("Verified OnlineJobs sender or owner-imported platform conversation")
        if alert:
            intent = "notification"
    elif known:
        category = "direct_client"
        evidence.append("Matched an existing business conversation")
    elif re.search(r"unsubscribe|newsletter|verification code|one.time (?:code|password)|password reset", text) and intent not in {"optout", "bounce"}:
        category = "other"
        evidence.append("Bulk or account-service message")
    elif intent in {"loom_requested", "meeting_requested", "proposal_requested"} or re.search(r"\b(?:project|proposal|automation|gohighlevel|client|hire|hiring|freelance)\b", text) or (business_email(sender) and re.match(r"\s*re\s*:", subject, re.I)):
        category = "needs_review"
        evidence.append("Possible business message; source or relationship needs confirmation")
    else:
        category = "other"
        evidence.append("No supported business-conversation signal")
    if outbound:
        intent = "reply" if known else "unknown"
    return {"category": category, "intent": intent, "reason": "; ".join(evidence),
            "evidence_excerpt": top[:300], "method": "rules", "confidence": 1.0 if platform or known else 0.5}


def normalize(message, *, known=False):
    headers = _headers(message)
    _validate_mime(message["payload"], str(message.get("id", "")))
    labels = message.get("labelIds", [])
    if not isinstance(labels, list):
        raise ValueError("Invalid Gmail labels")
    if set(labels) & {"SPAM", "TRASH", "DRAFT"}:
        return None
    sender_list = [addr.lower() for _, addr in getaddresses([headers["from"]]) if addr]
    if len(sender_list) != 1 or not EMAIL_RE.fullmatch(sender_list[0]):
        raise ValueError("Ambiguous Gmail sender")
    sender = sender_list[0]
    recipients = [a.lower() for _, a in getaddresses([headers.get("to", ""), headers.get("cc", "")]) if EMAIL_RE.fullmatch(a)]
    outbound = "SENT" in labels or sender == OWNER_EMAIL
    body = _body(message)[:32000]
    domain = sender.split("@")[-1]
    # Trust only an exact domain and Gmail's authentication results, never display names/body text.
    auth = next((h.get("value", "") for h in message["payload"].get("headers", [])
                 if h.get("name", "").lower() == "authentication-results" and
                 re.match(r"\s*mx\.google\.com;", h.get("value", ""), re.I)), "")
    # Require domain alignment, not merely another domain's passing signature.
    aligned = any(re.search(r"\b(?:dkim|spf|dmarc)=pass\b", part, re.I) and
                  re.search(r"(?:header\.(?:i|d|from)|smtp\.mailfrom)\s*=\s*(?:[^\s;@]+@|@)?(?:[\w-]+\.)*onlinejobs\.ph(?:\s|$)", part.strip(), re.I)
                  for part in auth.split(";"))
    platform = (domain == "onlinejobs.ph" or domain.endswith(".onlinejobs.ph")) and aligned
    classification = classify(headers["subject"], body, sender, platform=platform, outbound=outbound, known=known)
    if not body.strip() and not outbound:
        classification.update(category="needs_review", reason="Message body unavailable; open the original conversation")
    if (domain == "onlinejobs.ph" or domain.endswith(".onlinejobs.ph")) and not platform:
        classification.update(category="needs_review", reason="OnlineJobs sender authentication requires review")
    correspondent = (recipients[0] if len(recipients) == 1 else "") if outbound else sender
    reply_email = correspondent if business_email(correspondent) else ""
    if platform:
        # Suggested addresses in notifications never become send authority automatically.
        reply_email = ""
    provider_id, thread_id = message.get("id"), message.get("threadId")
    if not isinstance(provider_id, str) or not provider_id or not isinstance(thread_id, str) or not thread_id:
        raise ValueError("Gmail identities missing")
    return {"provider_id": provider_id, "thread_id": thread_id, "channel": "gmail",
            "direction": "out" if outbound else "in", "sender": sender, "recipients": recipients,
            "subject": headers["subject"][:998], "body": body, "occurred_at": _timestamp(message),
            "rfc_message_id": headers.get("message-id", ""), "references_header": headers.get("references", ""),
            "in_reply_to": headers.get("in-reply-to", ""), "platform_reference": platform_reference(body) if platform else "",
            "acquisition_source": "onlinejobs" if platform else "unknown", "reply_email": reply_email,
            "reply_verified": bool(reply_email and not outbound), "classification": classification,
            "needs_platform_import": platform and (not body.strip() or bool(re.search(r"(?:log in|login|sign in|click here) to (?:read|view)", body, re.I))),
            "delivery_recipient": (re.search(r"(?im)^Final-Recipient:\s*(?:rfc822;)?\s*([^\s;<>]+@[^\s;<>]+)", body).group(1).lower()
                                   if re.search(r"(?im)^Final-Recipient:\s*(?:rfc822;)?\s*([^\s;<>]+@[^\s;<>]+)", body) else "")}


class InboxSync:
    def __init__(self, gmail, database):
        self.gmail, self.db = gmail, database

    def run(self):
        try:
            profile = self.gmail.verify()  # Before any mailbox read, even if previously connected.
        except Exception:
            self.db.rpc("client_finder_inbox_error", {})
            raise
        lease = self.db.rpc("client_finder_inbox_start", {"mailbox_email": OWNER_EMAIL})
        if not isinstance(lease, dict) or not lease.get("lease_id"):
            raise ProviderError("Inbox sync already running or not configured")
        count = 0
        try:
            cursor = lease.get("history_id")
            full = not cursor
            if cursor:
                try:
                    count, cursor = self._history(str(cursor))
                except GmailError as exc:
                    if exc.status != 404:
                        raise
                    full = True
            if full:
                # Anchor at profile BEFORE listing. The next history sync replays arrivals during this scan.
                cursor = str(profile["historyId"])
                # Expired history requires a full rescan of the retained window,
                # including older messages imported/backdated since the last sync.
                since = datetime.fromisoformat(lease["backfill_start"].replace("Z", "+00:00"))
                count = self._full(int(since.timestamp()))
                if lease.get("history_id"):
                    self._refresh_retained()
            self.db.rpc("client_finder_inbox_finish", {
                "lease_id": lease["lease_id"], "history_id": str(cursor), "fetched_count": count, "error_code": None})
            return {"status": "complete", "fetched": count, "mailbox": OWNER_EMAIL}
        except Exception:
            self.db.rpc("client_finder_inbox_finish", {
                "lease_id": lease["lease_id"], "history_id": None, "fetched_count": count, "error_code": "sync_failed"})
            raise

    def _store(self, mid):
        try:
            raw = self.gmail.get("/messages/" + mid, format="full")
        except GmailError as exc:
            if exc.status != 404:
                raise
            self.db.rpc("client_finder_inbox_delete", {"provider_id": mid})
            return
        known = self.db.rows("client_finder_conversations", {"gmail_thread_id": "eq." + raw.get("threadId", "")}, select="id,category")
        item = normalize(raw, known=any(x["category"] in {"onlinejobs_conversation", "direct_client"} for x in known))
        if item is None:
            self.db.rpc("client_finder_inbox_delete", {"provider_id": mid})
        else:
            self.db.rpc("client_finder_inbox_ingest", {"item": item})

    def _full(self, since):
        token, seen, count = None, set(), 0
        while True:
            query = {"q": f"after:{since} -in:spam -in:trash -in:drafts", "maxResults": 100, "includeSpamTrash": "false"}
            if token:
                query["pageToken"] = token
            page = self.gmail.get("/messages", **query)
            for item in page.get("messages", []):
                self._store(item["id"])
                count += 1
            token = page.get("nextPageToken")
            if not token:
                return count
            if token in seen or len(seen) >= 1000:
                raise ProviderError("Gmail pagination did not complete")
            seen.add(token)

    def _refresh_retained(self):
        # Full listing excludes Trash/Spam. Recheck stored IDs too, so a missed
        # deletion or label change cannot leave stale reply authority behind.
        after = None
        while True:
            filters = {"channel": "eq.gmail", "order": "id.asc", "limit": "200"}
            if after:
                filters["id"] = "gt." + after
            rows = self.db.rows("client_finder_inbox_messages", filters, select="id,provider_id")
            for row in rows:
                self._store(row["provider_id"])
            if len(rows) < 200:
                return
            after = rows[-1]["id"]

    def _history(self, cursor):
        token, seen, count = None, set(), 0
        while True:
            query = {"startHistoryId": cursor, "maxResults": 100}
            if token:
                query["pageToken"] = token
            page = self.gmail.get("/history", **query)
            ids = set()
            for event in page.get("history", []):
                for key in ("messagesAdded", "labelsAdded", "labelsRemoved", "messagesDeleted"):
                    ids.update(x["message"]["id"] for x in event.get(key, []))
            for mid in sorted(ids):
                self._store(mid)
                count += 1
            token = page.get("nextPageToken")
            if not token:
                if not str(page.get("historyId", "")).isdigit():
                    raise ProviderError("Gmail checkpoint missing")
                return count, str(page["historyId"])
            if token in seen or len(seen) >= 1000:
                raise ProviderError("Gmail history pagination did not complete")
            seen.add(token)
