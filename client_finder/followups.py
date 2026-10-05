"""Create one review-only follow-up after a confirmed initial email is due."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .cards import stored_card
from .providers import ProviderError, SupabaseRest


MANILA = ZoneInfo("Asia/Manila")
PAGE_SIZE = 100


def _due_after_five_weekdays(sent_at: Any, now: datetime) -> bool:
    if not isinstance(sent_at, str):
        raise ValueError("confirmed send time is missing")
    try:
        sent = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("confirmed send time is malformed") from exc
    if sent.tzinfo is None:
        raise ValueError("confirmed send time has no timezone")
    if now.tzinfo is None:
        raise ValueError("current time has no timezone")
    due = sent.astimezone(MANILA)
    weekdays = 0
    while weekdays < 5:
        due += timedelta(days=1)
        if due.weekday() < 5:
            weekdays += 1
    return now.astimezone(MANILA) >= due


def prepare_due_followups(database: SupabaseRest, *, limit: int = 5) -> dict[str, Any]:
    if not 1 <= limit <= 5:
        raise ValueError("Follow-up limit must be 1 to 5")
    settings = database.rows("client_finder_settings", {"id": "eq.1"})
    if len(settings) != 1:
        raise ProviderError("Client Finder settings are unavailable")
    sender = settings[0]
    required = ("sender_name", "postal_address", "commercial_label", "opt_out_route")
    if any(not str(sender.get(key) or "").strip() for key in required):
        return {"status": "needs_attention", "cards": [],
                "diagnostics": ["Sender details are incomplete; no follow-up drafts created"],
                "diagnostic_count": 1}
    cards: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    now = datetime.now(MANILA)
    offset = 0
    while len(cards) < limit:
        initial = database.rows("client_finder_messages", {
            "kind": "eq.initial", "status": "eq.sent", "order": "sent_at.asc,id.asc",
            "limit": str(PAGE_SIZE), "offset": str(offset),
        }, select="id,lead_id,subject,observed_need,deliverable_id,sent_at")
        if len(initial) > PAGE_SIZE:
            raise ProviderError("Follow-up candidate page exceeded its limit")
        if not initial:
            break
        due: list[dict[str, Any]] = []
        reached_future = False
        for parent in initial:
            parent_id = str(parent.get("id") or "")
            if not parent_id:
                diagnostics.append("Confirmed initial message has no ID")
                continue
            try:
                if not _due_after_five_weekdays(parent.get("sent_at"), now):
                    reached_future = True
                    break
            except ValueError as exc:
                diagnostics.append(f"{parent_id}: {exc}")
                continue
            due.append(parent)
        existing_by_parent: dict[str, list[dict[str, Any]]] = {}
        if due:
            parent_ids = ",".join(str(parent["id"]) for parent in due)
            existing_rows = database.rows("client_finder_messages", {
                "parent_message_id": f"in.({parent_ids})"
            }, select="id,status,parent_message_id")
            for row in existing_rows:
                existing_by_parent.setdefault(str(row["parent_message_id"]), []).append(row)
        for parent in due:
            if len(cards) >= limit:
                break
            parent_id = str(parent["id"])
            existing = existing_by_parent.get(parent_id, [])
            if existing:
                if len(existing) == 1 and existing[0].get("status") == "draft":
                    try:
                        card = stored_card(database, str(existing[0]["id"]))
                        card["ready_for_approval"] = True
                        cards.append(card)
                    except ProviderError as exc:
                        diagnostics.append(f"{parent_id}: {exc}")
                elif len(existing) > 1:
                    diagnostics.append(f"{parent_id}: multiple follow-ups require review")
                continue
            deliverables = database.rows("client_finder_deliverables", {
                "id": f"eq.{parent['deliverable_id']}"
            }, select="scope_text")
            if len(deliverables) != 1:
                diagnostics.append(f"{parent_id}: deliverable missing")
                continue
            scope = str(deliverables[0]["scope_text"]).strip()
            if not scope or len(scope) > 220:
                diagnostics.append(f"{parent_id}: deliverable scope needs review")
                continue
            leads = database.rows("cold_leads", {"id": f"eq.{parent['lead_id']}"}, select="company_name")
            if len(leads) != 1:
                diagnostics.append(f"{parent_id}: lead missing")
                continue
            company = str(leads[0]["company_name"]).strip()[:80]
            subject = f"Checking back on a project idea for {company}"[:120]
            body = (
                "Hi there,\n\n"
                f"I'm checking back on my earlier note about {scope}. "
                "If a short outline for one project would be useful, I can send it over.\n\n"
                f"{str(sender['sender_name']).strip()}\n"
                f"{str(sender['postal_address']).strip()}\n"
                f"{str(sender['commercial_label']).strip()}\n"
                f"{str(sender['opt_out_route']).strip()}"
            )
            try:
                message = database.rpc("client_finder_create_due_followup", {
                    "initial_message_id": parent["id"], "subject": subject, "body": body,
                })
                if not isinstance(message, dict) or not message.get("id"):
                    raise ProviderError("Follow-up draft was not acknowledged")
                card = stored_card(database, str(message["id"]))
                card["ready_for_approval"] = True
                cards.append(card)
            except ProviderError as exc:
                diagnostics.append(f"{parent_id}: {exc}")
        if reached_future or len(initial) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return {"status": "needs_attention" if diagnostics else "complete", "cards": cards,
            "diagnostics": diagnostics[:25], "diagnostic_count": len(diagnostics)}
