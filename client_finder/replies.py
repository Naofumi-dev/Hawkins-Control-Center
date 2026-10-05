"""Deliver only reserved approved replies; never automatically retry an uncertain send."""
from .gmail import Gmail
from .providers import ProviderError


def send_one_reply(database, gmail=None, *, _outreach=False):
    gmail = gmail or Gmail.from_environment()
    gmail.verify()  # Wrong-account failures happen before claiming a delivery.
    database.rpc("client_finder_mark_stale_attempts", {})
    rows = database.rows("client_finder_send_attempts", {"send_class": "eq.outreach" if _outreach else "eq.reply", "status": "eq.claimed", "order": "claimed_at.asc", "limit": "5" if _outreach else "1"})
    if _outreach:
        # The legacy Telegram workflow owns its own immediate delivery path.
        rows = [a for a in rows if a.get("rfc_message_id") and database.rows("client_finder_messages",{"id":"eq."+a["message_id"],"approved_via":"eq.web"})]
    if not rows:
        return {"status": "idle"}
    attempt_id = rows[0]["id"]
    started = False
    def begin():
        nonlocal started
        attempt = database.rpc("client_finder_begin_send" if _outreach else "client_finder_reply_begin", {"attempt_id": attempt_id})
        started = bool(attempt)
        return attempt
    try:
        result = gmail.send(rows[0], before_send=begin)
        if result.get("canceled"):
            return {"status": "canceled"}
        if not result.get("id") or not result.get("threadId"):
            raise ProviderError("Gmail result identifiers missing")
        database.rpc("client_finder_complete_send" if _outreach else "client_finder_complete_reply", {"attempt_id": attempt_id,
            "gmail_message_id": result["id"], "gmail_thread_id": result["threadId"]})
        return {"status": "sent", "attempt_id": attempt_id}
    except Exception:
        if not started:
            # A failed identity/claim must never start Gmail delivery. A DB
            # timeout during begin is reconciled by the stalled-attempt sweep.
            raise
        # A DB failure after acceptance has exactly the same uncertainty as a timeout.
        database.rpc("client_finder_mark_send_unknown", {"attempt_id": attempt_id})
        return {"status": "send_unknown", "attempt_id": attempt_id}


def reconcile_reply(database, attempt_id, gmail=None, *, _outreach=False):
    gmail = gmail or Gmail.from_environment()
    gmail.verify()
    rows = database.rows("client_finder_send_attempts", {"id": "eq."+attempt_id, "send_class": "eq.outreach" if _outreach else "eq.reply", "status": "eq.send_unknown"})
    if len(rows)!=1 or not rows[0].get("rfc_message_id"):
        raise ValueError("An uncertain reply attempt is required")
    attempt = rows[0]
    result = gmail.get("/messages", q="in:sent rfc822msgid:"+attempt["rfc_message_id"], maxResults=10)
    candidates = result.get("messages", [])
    if len(candidates)!=1 or result.get("nextPageToken"):
        return {"status": "needs_checking", "reason": "Sent search is not conclusive; no resend authorized"}
    from .inbox import normalize
    raw = gmail.get("/messages/"+candidates[0]["id"], format="full")
    message = normalize(raw)
    if not message or message["direction"]!="out" or message["rfc_message_id"]!=attempt["rfc_message_id"] or \
       message["recipients"]!=[attempt["recipient_email"]] or message["subject"]!=attempt["subject"] or \
       message["body"].replace('\r\n','\n').rstrip('\n')!=attempt["body"].replace('\r\n','\n').rstrip('\n'):
        return {"status": "needs_checking", "reason": "Sent payload mismatch"}
    database.rpc("client_finder_complete_send" if _outreach else "client_finder_complete_reply", {"attempt_id": attempt_id,
        "gmail_message_id": raw["id"], "gmail_thread_id": raw["threadId"]})
    return {"status": "sent", "attempt_id": attempt_id}
