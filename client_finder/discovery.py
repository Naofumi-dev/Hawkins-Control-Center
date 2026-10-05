"""Agency search to review-card orchestration. This module never sends email."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .drafting import card_text, make_draft
from .cards import stored_card
from .providers import BraveSearch, ProviderError, SupabaseRest
from .research import ResearchError, SafeSiteFetcher, UnsafeDestination, public_url, research_site


SEARCH_QUERIES = (
    '"digital agency" "we are hiring" "client portal" United States',
    '"marketing agency" "seeking" "proposal" United States',
    '"digital agency" "client portal" United States contact',
    '"marketing agency" "lead generation" United States contact',
    '"web agency" "proposal" United States contact',
    '"digital agency" "RFP" United States contact',
)
EXCLUDED_HOSTS = (
    "linkedin.com", "facebook.com", "instagram.com", "upwork.com", "onlinejobs.ph",
    "clutch.co", "designrush.com", "goodfirms.co", "yelp.com", "reddit.com",
    "indeed.com", "glassdoor.com", "wikipedia.org", "medium.com", "youtube.com",
)


@dataclass
class DiscoveryResult:
    cards: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    searched: int = 0
    inspected: int = 0

    def json(self) -> dict[str, Any]:
        return {"cards": self.cards, "diagnostics": self.diagnostics[:25], "searched": self.searched, "inspected": self.inspected}


def _root_url(value: str) -> str:
    checked = public_url(value)
    parsed = urlsplit(checked)
    host = parsed.hostname or ""
    if any(host == blocked or host.endswith("." + blocked) for blocked in EXCLUDED_HOSTS):
        raise UnsafeDestination("Search result is a restricted platform or directory")
    return urlunsplit((parsed.scheme, parsed.netloc, "/", "", ""))


class DiscoveryRunner:
    def __init__(self, database: SupabaseRest, search: BraveSearch, *, fetcher: SafeSiteFetcher | None = None) -> None:
        self.database = database
        self.search = search
        self.fetcher = fetcher or SafeSiteFetcher()

    def _settings(self) -> dict[str, Any]:
        rows = self.database.rows("client_finder_settings", {"id": "eq.1"})
        if len(rows) != 1:
            raise ProviderError("Client Finder settings are missing or duplicated")
        return rows[0]

    def _existing_lead(self, domain: str) -> dict[str, Any] | None:
        for variant in (domain, "www." + domain):
            rows = self.database.rows("cold_leads", {"company_domain": f"ilike.{variant}"}, select="id,db_source,status,contact_email")
            if rows:
                return rows[0]
        return None

    def _contact_used(self, email: str) -> bool:
        rows = self.database.rows("cold_leads", {"contact_email": f"eq.{email}"}, select="id")
        return bool(rows)

    def _create_lead(self, research, draft) -> dict[str, Any]:
        return self.database.insert("cold_leads", {
            "niche": "agencies", "db_source": "client_finder_brave",
            "company_name": research.company_name, "company_domain": research.domain,
            "company_url": research.company_url, "location": research.location,
            "contact_email": research.contact_email, "email_verified": False,
            "verification_result": "mx_unchecked", "status": "enriched",
            "company_info": {
                "location_source_url": research.location_source_url,
                "contact_source_url": research.contact_source_url,
                "observations": [vars(item) for item in research.observations],
            },
            "research_summary": draft.observed_need,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        })

    def run(self, *, limit: int = 5, preview: bool = False) -> DiscoveryResult:
        if not 1 <= limit <= (10 if preview else 5):
            raise ValueError("Discovery limit is outside the agreed range")
        settings = self._settings()
        result = DiscoveryResult()
        if not preview and not settings.get("discovery_enabled", False):
            result.diagnostics.append("Daily discovery is disabled in settings")
            return result
        seen: set[str] = set()
        for query in SEARCH_QUERIES:
            if len(result.cards) >= limit or result.inspected >= 24:
                break
            hits = self.search.search(query)
            result.searched += 1
            for hit in hits:
                if len(result.cards) >= limit or result.inspected >= 24:
                    break
                try:
                    source_url = public_url(hit.url)
                    root = _root_url(source_url)
                    domain = (urlsplit(root).hostname or "").removeprefix("www.")
                    if domain in seen:
                        continue
                    seen.add(domain)
                    existing = self._existing_lead(domain)
                    if existing and not preview:
                        if existing.get("db_source") != "client_finder_brave" or existing.get("status") != "enriched":
                            continue
                        messages = self.database.rows("client_finder_messages", {"lead_id": f"eq.{existing['id']}"}, select="id,status")
                        if messages:
                            if len(messages) == 1 and messages[0].get("status") == "draft":
                                pending = stored_card(self.database, str(messages[0]["id"]))
                                pending["ready_for_approval"] = True
                                result.cards.append(pending)
                            continue
                    research = research_site(
                        root, fetcher=self.fetcher,
                        observed_at=datetime.now(timezone.utc).isoformat(),
                        focus_url=source_url,
                    )
                    result.inspected += 1
                    if research.needs_review and not preview:
                        task = self.database.rpc("client_finder_record_research_task", {
                            "domain": research.domain,
                            "company_url": research.company_url,
                            "company_name": research.company_name,
                            "source_url": source_url,
                            "reason": "; ".join(research.needs_review)[:500],
                        })
                        if not isinstance(task, dict) or task.get("domain") != research.domain:
                            raise ProviderError("Research task was not acknowledged")
                    draft = make_draft(
                        research,
                        sender_name=str(settings.get("sender_name") or ""),
                        sender_address=str(settings.get("postal_address") or ""),
                        commercial_label=str(settings.get("commercial_label") or ""),
                        opt_out_route=str(settings.get("opt_out_route") or ""),
                    )
                    if draft is None:
                        result.diagnostics.append(f"{domain}: no supported deliverable matched published evidence")
                        continue
                    review_card = card_text(draft, research)
                    if preview:
                        preview_card = review_card
                        if preview_card.startswith("Ready for approval"):
                            preview_card = preview_card.replace("Ready for approval", "Research preview only: no review card is stored", 1)
                        result.cards.append({"message_id": None, "revision": None, "kind": "initial", "card_text": preview_card, "ready_for_approval": False})
                        continue
                    if not draft.ready_for_approval:
                        result.diagnostics.append(f"{domain}: {'; '.join(draft.review_reasons)}")
                        continue
                    if self._contact_used(research.contact_email) and not existing:
                        result.diagnostics.append(f"{domain}: contact already belongs to a Hawkins lead")
                        continue
                    lead = existing or self._create_lead(research, draft)
                    message = self.database.rpc("client_finder_create_message", {
                        "lead_id": lead["id"], "recipient_email": draft.recipient,
                        "subject": draft.subject, "body": draft.body,
                        "evidence": {
                            "contact_source_url": research.contact_source_url,
                            "observation_source_url": draft.evidence_url,
                            "us_location_source_url": research.location_source_url,
                            "observed_at": draft.evidence_date,
                            "observation": draft.observed_need,
                            "signal_type": draft.signal_type,
                        },
                        "observed_need": draft.observed_need,
                        "deliverable_id": draft.deliverable_id, "proof_id": draft.proof_id,
                        "kind": "initial", "parent_message_id": None,
                    })
                    if not isinstance(message, dict) or not message.get("id"):
                        raise ProviderError("Message creation did not return an ID")
                    result.cards.append({
                        "message_id": message["id"], "revision": message["revision"],
                        "kind": "initial", "card_text": review_card, "ready_for_approval": True,
                    })
                except (ResearchError, ProviderError, ValueError) as exc:
                    result.diagnostics.append(f"{hit.url[:160]}: {exc}")
        return result
