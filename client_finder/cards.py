"""Re-render the full stored draft after an owner edit."""

from __future__ import annotations

import uuid
from typing import Any

from .providers import ProviderError, SupabaseRest


def stored_card(database: SupabaseRest, message_id: str) -> dict[str, Any]:
    uuid.UUID(message_id)
    messages = database.rows("client_finder_messages", {"id": f"eq.{message_id}"})
    if len(messages) != 1:
        raise ProviderError("Stored message was not found")
    message = messages[0]
    if message.get("status") not in ("draft", "pending_review"):
        raise ProviderError("Stored message is not awaiting a review card")
    leads = database.rows("cold_leads", {"id": f"eq.{message['lead_id']}"}, select="id,company_name,company_url,company_domain,location,contact_name,contact_title")
    proofs = database.rows("client_finder_proofs", {"id": f"eq.{message['proof_id']}"}, select="id,title,proof_url,proof_kind")
    deliverables = database.rows("client_finder_deliverables", {"id": f"eq.{message['deliverable_id']}"}, select="id,scope_text")
    if len(leads) != 1 or len(proofs) != 1 or len(deliverables) != 1:
        raise ProviderError("Stored card references incomplete research or proof")
    lead, proof, deliverable = leads[0], proofs[0], deliverables[0]
    evidence = message["evidence"]
    name = lead.get("contact_name") or "General company inbox"
    title = f" ({lead['contact_title']})" if lead.get("contact_title") else ""
    card = (
        f"{'Follow-up draft' if message['kind'] == 'followup' else 'Initial outreach draft'}: ready for approval\n\n"
        f"Agency: {lead['company_name']}\nWebsite: {lead['company_url']}\n"
        f"US location: {lead.get('location') or 'unconfirmed'} ({evidence.get('us_location_source_url')})\n"
        f"Observed ({str(evidence.get('signal_type') or 'service').replace('_', ' ')}): {message['observed_need']}\n"
        f"Source: {evidence.get('observation_source_url')} ({evidence.get('observed_at')})\n"
        f"Contact: {name}{title}, {message['recipient_email']}\n"
        f"Email source: {evidence.get('contact_source_url')}\n"
        f"Proposed result: {deliverable['scope_text']}\n"
        f"Relevant proof: {proof['title']} ({proof['proof_kind']}), {proof['proof_url']}\n\n"
        f"Exact recipient: {message['recipient_email']}\n"
        f"Exact subject: {message['subject']}\n\nExact body:\n{message['body']}"
    )
    if len(card) > 4000:
        raise ProviderError("Edited card exceeds the Telegram message limit")
    return {"message_id": message["id"], "revision": message["revision"], "kind": message["kind"], "card_text": card}
