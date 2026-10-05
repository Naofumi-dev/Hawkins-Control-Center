"""Select a supported deliverable and build a factual review draft."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .research import Observation, SiteResearch


CATALOG = Path(__file__).resolve().parents[1] / "data" / "deliverables.json"


@dataclass(frozen=True)
class Draft:
    company_name: str
    recipient: str
    subject: str
    body: str
    observed_need: str
    signal_type: str
    evidence_url: str
    evidence_date: str
    deliverable: str
    deliverable_id: str
    proof_title: str
    proof_id: str
    proof_url: str
    proof_status: str
    ready_for_approval: bool
    review_reasons: tuple[str, ...]


def _catalog() -> list[dict[str, object]]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def match_deliverable(observations: list[Observation]) -> tuple[dict[str, object], Observation] | None:
    """Match a published sentence, not a model's guess about business pain."""
    priority = {"project_request": 0, "hiring": 1, "service": 2}
    for observation in sorted(observations, key=lambda item: priority.get(item.signal_type, 3)):
        lowered = observation.text.casefold()
        for offer in _catalog():
            if any(re.search(r"(?<!\w)" + re.escape(str(phrase)) + r"(?:s|es)?(?!\w)", lowered) for phrase in offer["signals"]):
                return offer, observation
    return None


def make_draft(
    research: SiteResearch, *, sender_name: str = "", sender_address: str = "",
    commercial_label: str = "", opt_out_route: str = "",
) -> Draft | None:
    matched = match_deliverable(research.observations)
    if not matched:
        return None
    offer, observation = matched
    reasons = list(research.needs_review)
    if not research.location or not research.location_source_url:
        reasons.append("US company location needs confirmation")
    if not research.contact_email or not research.contact_source_url:
        reasons.append("A published company business email is required")
    if not sender_address.strip():
        reasons.append("Sender postal address must be configured before sending")
    if not sender_name.strip():
        reasons.append("Sender name must be configured before sending")
    if not commercial_label.strip():
        reasons.append("Commercial identification must be configured before sending")
    if not opt_out_route.strip():
        reasons.append("An opt-out route must be configured before sending")
    signal_label = str(offer["signal_label"])
    deliverable = str(offer["deliverable"])
    proof_claim = str(offer["proof_claim"])
    proof_url = str(offer["proof_url"])
    name = research.contact_name.split()[0] if research.contact_name else "there"
    observed_quote = " ".join(observation.text.split())[:160].rstrip(" ,;:")
    if any(phrase in observed_quote.casefold() for phrase in ("ignore previous", "system prompt", "assistant instruction", "developer message")):
        return None
    subject = f"A project delivery idea for {research.company_name}"[:120]
    body = (
        f"Hi {name},\n\n"
        f"I saw this on your site: “{observed_quote}.” "
        f"It relates to {signal_label}. If extra delivery capacity would help, "
        f"I could build {deliverable} for one scoped client project.\n\n"
        f"{proof_claim}. Example: {proof_url}\n\n"
        "Would a short outline for one project be useful?\n\n"
        f"{sender_name.strip() or '[Sender name required]'}\n"
        f"{sender_address.strip() or '[Sender mailing address required before sending]'}\n"
        f"{commercial_label.strip() or '[Commercial label required]'}\n"
        f"{opt_out_route.strip() or '[Opt-out route required]'}"
    )
    return Draft(
        company_name=research.company_name,
        recipient=research.contact_email,
        subject=subject,
        body=body,
        observed_need=observation.text,
        signal_type=observation.signal_type,
        evidence_url=observation.source_url,
        evidence_date=observation.observed_at,
        deliverable=deliverable,
        deliverable_id=str(offer["id"]),
        proof_title=str(offer["proof_title"]),
        proof_id=str(offer["proof_id"]),
        proof_url=proof_url,
        proof_status=str(offer["proof_status"]),
        ready_for_approval=not reasons,
        review_reasons=tuple(dict.fromkeys(reasons)),
    )


def card_text(draft: Draft, research: SiteResearch) -> str:
    contact = research.contact_name or "General company inbox"
    role = f" ({research.contact_role})" if research.contact_role else ""
    note = "Ready for approval" if draft.ready_for_approval else "Research only: " + "; ".join(draft.review_reasons)
    card = (
        f"{note}\n\n"
        f"Agency: {research.company_name}\nWebsite: {research.company_url}\n"
        f"US location: {research.location or 'unconfirmed'} ({research.location_source_url or 'no source'})\n"
        f"Observed ({draft.signal_type.replace('_', ' ')}): {draft.observed_need}\nSource: {draft.evidence_url} ({draft.evidence_date})\n"
        f"Contact: {contact}{role}, {draft.recipient or 'no published business email'}\n"
        f"Email source: {research.contact_source_url or 'none'}\n"
        f"Proposed result: {draft.deliverable}\n"
        f"Relevant proof: {draft.proof_title} ({draft.proof_status}), {draft.proof_url}\n\n"
        f"Exact recipient: {draft.recipient or 'missing'}\n"
        f"Exact subject: {draft.subject}\n\nExact body:\n{draft.body}"
    )
    if len(card) > 4000:
        raise ValueError("Review card is too long for Telegram; edit the draft before presenting it")
    return card
