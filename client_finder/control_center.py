"""Owner-only command-center API, independent of internal service credentials."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .gmail import OWNER_EMAIL, request_json
from .inbox import CATEGORIES, STAGES, classify, business_email, platform_reference
from .providers import EXPECTED_SUPABASE_URL, ProviderConfigurationError, ProviderError


class OwnerError(Exception):
    pass


def authenticate_owner(authorization, database):
    """Validate through the owned Supabase Auth server, never decode an unverified JWT."""
    if not authorization.startswith("Bearer ") or len(authorization) > 8192:
        raise OwnerError("Owner sign-in required")
    expected_id = os.environ.get("CLIENT_FINDER_OWNER_AUTH_ID", "")
    if not expected_id:
        raise ProviderConfigurationError("Owner Auth ID is not configured")
    user = request_json(EXPECTED_SUPABASE_URL + "/auth/v1/user", headers={
        "apikey": database.headers["apikey"], "Authorization": authorization})
    if (user.get("email", "").lower() != OWNER_EMAIL or user.get("id") != expected_id or
            not user.get("email_confirmed_at")):
        raise OwnerError("This workspace is restricted to the personal owner")
    return str(uuid.UUID(user["id"]))


def _id(value):
    return str(uuid.UUID(str(value)))


def manual_import(data, actor):
    reference = str(data.get("platform_reference", ""))
    if (platform_reference(reference) != reference or len(reference) > 2000 or
            not re.search(r"/(?:message|messages|conversation|conversations)/", urlsplit(reference).path, re.I)):
        raise ValueError("Use the exact OnlineJobs conversation URL")
    body, subject = str(data.get("body", "")).strip(), str(data.get("subject", "")).strip()
    if not body or len(body) > 32000 or not subject or len(subject)>998 or "\n" in subject or "\r" in subject:
        raise ValueError("Conversation subject and full message are required")
    recipient = str(data.get("reply_email", "")).lower().strip()
    if recipient and (not business_email(recipient) or data.get("recipient_confirmed") is not True):
        raise ValueError("Confirm the contact's explicitly provided email address")
    at = datetime.fromisoformat(str(data.get("occurred_at", "")).replace("Z", "+00:00"))
    if at.tzinfo is None or at > datetime.now(timezone.utc):
        raise ValueError("Use the message's actual timestamp with timezone")
    stable = hashlib.sha256((reference+"\n"+at.isoformat()+"\n"+body).encode()).hexdigest()
    classification = classify(subject, body, recipient, platform=True)
    prior = str(data.get("prior_context", "")).strip()
    if len(prior) > 4000:
        raise ValueError("Prior context must be at most 4000 characters")
    # An owner may supply the preceding question when the answer says only yes.
    # Preserve that evidence separately instead of rewriting the client's words.
    if (classification["intent"] in {"unknown", "reply"} and
            re.search(r"\b(?:yes|of course|please (?:email|send|share))\b", body, re.I) and
            re.search(r"\bloom\b", prior, re.I)):
        classification.update(intent="loom_requested", prior_context=prior,
                              reason="Owner imported the positive reply and preceding Loom request")
    return {"provider_id": "onlinejobs:"+stable, "thread_id": "", "channel": "onlinejobs_import",
            "platform_reference": reference, "subject": subject, "body": body, "sender": recipient or "onlinejobs.ph",
            "recipients": [OWNER_EMAIL], "direction": "in", "occurred_at": at.isoformat(),
            "acquisition_source": "onlinejobs", "reply_email": recipient, "reply_verified": bool(recipient),
            "imported_by": actor, "classification": classification,
            "needs_platform_import": False}


class ControlCenter:
    def __init__(self, database, actor):
        self.db, self.actor = database, actor

    def snapshot(self):
        # Bounded lists; bodies load only when a conversation is selected.
        page = self.conversations()
        conversations = page["conversations"]
        tasks = self.db.rows("client_finder_tasks", {"order": "created_at.desc", "limit": "200"})
        opportunities = self.db.rows("client_finder_opportunities", {"order": "updated_at.desc", "limit": "200"})
        drafts = self.db.rows("client_finder_messages", {"kind": "eq.reply", "order": "updated_at.desc", "limit": "200"})
        mailboxes = self.db.rows("client_finder_mailboxes", {}, select="email,history_id,last_success_at,last_attempt_at,fetched_count,error_code,verified_at,replies_enabled,reply_limit")
        settings = self.db.rows("client_finder_settings", {"id": "eq.1"}, select="daily_send_limit,monthly_cost_cap_cents,sending_enabled,sending_pause_reason,sender_name,postal_address,commercial_label,opt_out_route")
        footer = "\n".join(str(settings[0].get(k) or "") for k in ("sender_name","postal_address","commercial_label","opt_out_route")) if settings else ""
        proofs = self.db.rows("client_finder_proofs", {"active": "eq.true", "verified_at": "not.is.null"})
        runs = self.db.rows("client_finder_agent_runs", {"order": "started_at.desc", "limit": "30"})
        return {"owner_email": OWNER_EMAIL, "conversations": conversations, "tasks": tasks,
                "opportunities": opportunities, "drafts": drafts, "mailbox": mailboxes[0] if mailboxes else None,
                "settings": settings[0] if settings else None, "sender_footer": footer.strip(), "proofs": proofs, "runs": runs,
                "statistics": self.db.rpc("client_finder_workspace_status", {}),
                "page_limit": 200, "next_before": page["next_before"]}

    def overview(self):
        return {"leads": self.db.count("cold_leads"),
                "contacted": self.db.count("cold_leads", {"first_sent_at": "not.is.null"}),
                "replied": self.db.count("cold_leads", {"replied_at": "not.is.null"}),
                "proofs": self.db.count("client_finder_proofs"),
                "deliverables": self.db.count("client_finder_deliverables")}

    def leads(self, search="", history="all", after_id=None):
        after_id = _id(after_id) if after_id else None
        search = search.strip()
        if len(search) > 160 or any(ord(c) < 32 for c in search):
            raise ValueError("Use a search phrase up to 160 characters")
        filters = {}
        if history == "contacted":
            filters["first_sent_at"] = "not.is.null"
        elif history == "uncontacted":
            filters["first_sent_at"] = "is.null"
        elif history == "replied":
            filters["replied_at"] = "not.is.null"
        elif history != "all":
            raise ValueError("Invalid contact history filter")
        if search:
            # Quote the value before the REST client percent-encodes the query.
            # Reserved filter syntax stays inside the value, never becomes an operator.
            value = search.replace("\\", "\\\\").replace('"', '\\"').replace("*", "%")
            filters["or"] = "(" + ",".join(f'{field}.ilike."%{value}%"' for field in
                ("company_name", "company_domain", "contact_name", "contact_email", "location", "niche")) + ")"
        total = self.db.count("cold_leads", dict(filters))
        if after_id:
            filters["id"] = "gt." + _id(after_id)
        rows = self.db.rows("cold_leads", {**filters, "order": "id.asc", "limit": "100"},
            select="id,company_name,company_domain,company_url,location,niche,db_source,contact_name,contact_title,contact_email,status,first_sent_at,replied_at")
        return {"leads": rows, "total": total, "next_after": rows[-1]["id"] if len(rows) == 100 else None}

    def lead(self, lead_id):
        lead_id = _id(lead_id)
        rows = self.db.rows("cold_leads", {"id": "eq."+lead_id},
            select="id,company_name,company_domain,company_url,location,niche,db_source,contact_name,contact_title,contact_email,email_verified,verification_result,research_summary,enriched_at,status,first_sent_at,replied_at")
        if not rows:
            raise ValueError("Lead not found")
        lead = rows[0]
        opportunities = self.db.rows("client_finder_opportunities", {"lead_id": "eq."+lead_id}, select="id")
        suppressions = []
        for scope, field in (("email", "contact_email"), ("domain", "company_domain")):
            if lead.get(field):
                suppressions.extend(self.db.rows("client_finder_suppressions", {
                    "scope": "eq."+scope, "value": "eq."+lead[field].strip().lower()}))
        return {"lead": lead, "suppressions": suppressions,
                "evidence": self.db.rows("client_finder_evidence", {"lead_id": "eq."+lead_id, "order": "observed_at.desc", "limit": "200"}),
                "drafts": self.db.rows("client_finder_messages", {"lead_id": "eq."+lead_id, "order": "created_at.desc", "limit": "200"},
                    select="id,kind,revision,recipient_email,subject,body,status,sent_at,gmail_message_id"),
                "conversations": self.db.rows("client_finder_conversations", {
                    "opportunity_id": "in.("+",".join(_id(o["id"]) for o in opportunities)+")"}) if opportunities else []}

    def library(self):
        registry = json.loads((Path(__file__).resolve().parents[1] / "data/source_registry.json").read_text())
        return {"proofs": self.db.rows("client_finder_proofs", {"order": "title.asc", "limit": "1000"}),
                "deliverables": self.db.rows("client_finder_deliverables", {"order": "title.asc", "limit": "1000"}),
                "sources": [{k: source[k] for k in ("name", "url", "category", "access_method", "enabled")}
                            for source in registry["sources"]],
                "source_rows": registry["row_count"], "catalog_limit": 1000}

    def conversations(self, before_time=None, before_id=None):
        filters = {"order": "last_message_at.desc,id.desc", "limit": "200"}
        if before_time or before_id:
            if not before_time or not before_id:
                raise ValueError("Incomplete pagination cursor")
            timestamp = datetime.fromisoformat(before_time.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("Cursor requires timezone")
            at, cid = timestamp.isoformat(), _id(before_id)
            filters["or"] = f"(last_message_at.lt.{at},and(last_message_at.eq.{at},id.lt.{cid}))"
        rows = self.db.rows("client_finder_conversations", filters)
        return {"conversations": rows, "next_before": {"time": rows[-1]["last_message_at"], "id": rows[-1]["id"]} if len(rows)==200 else None}

    def conversation(self, cid):
        cid = _id(cid)
        rows = self.db.rows("client_finder_conversations", {"id": "eq."+cid})
        if not rows:
            raise ValueError("Conversation not found")
        # Read newest context first; never truncate away the latest inbound item.
        messages = self.db.rows("client_finder_inbox_messages", {"conversation_id": "eq."+cid, "order": "occurred_at.desc,id.desc", "limit": "500"})
        tasks = self.db.rows("client_finder_tasks", {"conversation_id": "eq."+cid, "order": "created_at.desc", "limit": "200"})
        drafts = self.db.rows("client_finder_messages", {"conversation_id": "eq."+cid, "kind": "eq.reply", "order": "updated_at.desc", "limit": "200"})
        opportunities = self.db.rows("client_finder_opportunities", {"id": "eq."+rows[0]["opportunity_id"]}) if rows[0].get("opportunity_id") else []
        return {"conversation": rows[0], "messages": list(reversed(messages)), "tasks": tasks, "drafts": drafts, "opportunities": opportunities, "history_truncated": len(messages)==500}

    def action(self, path, data):
        if not isinstance(data, dict):
            raise ValueError("Object required")
        if path == "/api/inbox/import":
            return self.db.rpc("client_finder_inbox_ingest", {"item": manual_import(data, self.actor)})
        if path == "/api/classification":
            if data.get("category") not in CATEGORIES:
                raise ValueError("Invalid classification")
            return self.db.rpc("client_finder_correct_classification", {"conversation_id": _id(data["conversation_id"]),
                "category": data["category"], "reason": str(data.get("reason", ""))[:1000], "actor": self.actor})
        if path == "/api/stage":
            if data.get("stage") not in STAGES:
                raise ValueError("Invalid opportunity stage")
            return self.db.rpc("client_finder_set_stage", {"opportunity_id": _id(data["opportunity_id"]),
                "stage": data["stage"], "note": str(data.get("note", ""))[:2000], "actor": self.actor})
        if path == "/api/tasks/action":
            return self.db.rpc("client_finder_task_action", {"task_id": _id(data["task_id"]), "action": data.get("action"), "actor": self.actor})
        if path == "/api/drafts/save":
            revision = data.get("expected_revision")
            if not isinstance(revision, int) or isinstance(revision, bool) or revision<0:
                raise ValueError("Expected revision required")
            return self.db.rpc("client_finder_reply_save", {"conversation_id": _id(data["conversation_id"]),
                "expected_revision": revision, "subject": str(data.get("subject", "")), "body": str(data.get("body", "")),
                "proof_id": data.get("proof_id") or None, "actor": self.actor})
        if path == "/api/drafts/approve":
            revision = data.get("revision")
            if not isinstance(revision, int) or isinstance(revision, bool) or revision<1:
                raise ValueError("Exact revision required")
            return self.db.rpc("client_finder_reply_approve", {"message_id": _id(data["message_id"]),
                "revision": revision, "via": "web", "actor": self.actor})
        if path == "/api/suppress":
            return self.db.rpc("client_finder_conversation_suppress", {"conversation_id": _id(data["conversation_id"]), "actor": self.actor})
        raise ValueError("Unknown action")
