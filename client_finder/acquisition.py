"""Personal acquisition API. Imported/model content is data, never authority."""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from .control_center import _id
from .inbox import business_email
from .providers import ProviderError

WORKFLOWS = (
    ("V0xHCzfFMgKR61yh", "Dustin · OnlineJobs", "Job discovery"),
    ("hwEDWc0F9Wam1MgB", "Eleven + Steve · Score & Draft", "Qualification and cover letters"),
    ("x10lpGeWihYhpunW", "Hopper · Jobs API", "Legacy review and history"),
    ("TaSrrFcWgr0W0Yd7", "Client Finder · Discovery", "Agency research"),
    ("2PLgsImvFAGw0JTf", "Client Finder · Review & Send", "Exact revision approval"),
    ("VMx5m5ADmApXlkjU", "Client Finder · Inbox Monitor", "Replies and suppression"),
    ("G2EyMqtsewhrQJAG", "Client Finder · Follow-ups", "Eligible follow-ups"),
    ("saO2Ns7Qp604kcvm", "Hawkins · Prepare Proposals", "Calls into proposals"),
)
PROVIDERS = ("google", "notion", "n8n", "telegram", "onlinejobs", "calcom", "fathom", "ghl", "loom")


def text(value, maximum=2000, required=False):
    if not isinstance(value, str) or len(value)>maximum or "\x00" in value or (required and not value.strip()):
        raise ValueError("Invalid or missing text")
    return value.strip()


def safe_url(value):
    value = text(value, 2000, True)
    u = urlsplit(value)
    if (u.scheme != "https" or not u.hostname or u.username or u.password or u.port not in (None, 443)
            or any(ord(c)<33 for c in value) or "\\" in value or u.hostname in ("localhost", "127.0.0.1", "::1")
            or "." not in u.hostname):
        raise ValueError("Use a public HTTPS reference")
    # A reference is never fetched here. Provider adapters use fixed API hosts.
    return urlunsplit((u.scheme, u.netloc, u.path, u.query, ""))


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def normalize_job(data):
    source = safe_url(data.get("source_url", data.get("job_url", data.get("url", ""))))
    u = urlsplit(source)
    platform = "onlinejobs" if u.hostname in ("www.onlinejobs.ph", "onlinejobs.ph") else "manual"
    if platform == "onlinejobs":
        match = re.fullmatch(r"/jobseekers/job/(?:[^/]*-)?([0-9]+)/?", u.path)
        if not match:
            raise ValueError("Use the exact OnlineJobs job posting URL")
        key = "onlinejobs:"+match.group(1)
        source = urlunsplit(("https", "www.onlinejobs.ph", u.path.rstrip("/"), "", ""))
    else:
        key = "url:"+fingerprint(source)
    questions = data.get("questions", [])
    blockers = data.get("blockers", [])
    if not isinstance(questions, list) or len(questions)>25 or not isinstance(blockers, list) or len(blockers)>20:
        raise ValueError("Invalid job requirements")
    questions = [text(q, 1000, True) for q in questions]
    if len(set(questions)) != len(questions):
        raise ValueError("Duplicate screening question")
    contact = text(data.get("contact_email", ""), 254).lower()
    if contact and not business_email(contact):
        raise ValueError("Invalid contact address")
    applied = data.get("applied_at") or None
    if applied:
        dt = datetime.fromisoformat(text(applied, 80).replace("Z", "+00:00"))
        if dt.tzinfo is None or dt>datetime.now(timezone.utc):
            raise ValueError("Use a verified past application timestamp with timezone")
        applied = dt.isoformat()
    if str(data.get("status", "")).lower() in ("sent", "applied", "submitted", "interview", "offer", "hired") and not applied:
        blockers = [*blockers, "Historical application reported; reconcile submission evidence before applying"]
    return {"kind": "job", "job_key": key, "platform": platform, "source_url": source,
            "title": text(data.get("title", data.get("job_title", "")), 500, True),
            "company": text(data.get("company", "Unspecified"), 500, True),
            "description": text(data.get("description", data.get("overview", "")), 16000, True),
            "contact_email": contact or None, "source_confirmed": data.get("source_confirmed") is True,
            "questions": questions, "blockers": [text(x, 1000, True) for x in blockers], "applied_at": applied}


def normalize_resource(data):
    kind = data.get("kind")
    if kind not in ("resume", "proof", "profile", "proposal", "sheet", "notion", "calendar", "pipeline"):
        raise ValueError("Unsupported resource type")
    provider = data.get("provider", "manual")
    if provider not in (*PROVIDERS, "manual"):
        raise ValueError("Unsupported resource provider")
    url = safe_url(data["url"]) if data.get("url") else None
    if provider == "loom" and (not url or urlsplit(url).hostname not in ("loom.com", "www.loom.com") or not urlsplit(url).path.startswith("/share/")):
        raise ValueError("Use the reviewed Loom share link")
    if data.get("reviewed") is not True:
        raise ValueError("Review the resource and its claims before saving")
    content = text(data.get("content", ""), 12000)
    version = text(data.get("provider_version", ""), 200)
    return {"provider": provider, "external_id": text(data.get("external_id", url or kind), 2000, True),
            "kind": kind, "title": text(data.get("title", ""), 500, True), "url": url,
            "content": content, "reviewed": True, "version": fingerprint([url, content, version]),
            "metadata": {"provider_version": version,"proof_kind":"project" if data.get("proof_kind")=="project" else "prototype"}}


class Acquisition:
    def __init__(self, database, actor):
        self.db, self.actor = database, actor

    def command(self, op, data):
        return self.db.rpc("client_finder_acquisition_action", {"operation": op, "item": data, "actor": self.actor})

    def snapshot(self):
        fallback = [{"id": i, "name": n, "purpose": p, "active": None, "observed_at": None} for i,n,p in WORKFLOWS]
        try:
            connections = self.db.rows("client_finder_connections", {}, select="provider,identity,status,selected,enabled,verified_at,last_success_at,error_code,updated_at")
        except ProviderError:
            return {"ready": False, "error": "Acquisition database unavailable. Check connection and migrations 006–008.", "workflows": fallback}
        jobs = self.jobs()["jobs"]
        tasks = self.db.rows("client_finder_tasks", {"status": "in.(blocked,review,pending)", "order": "created_at.asc", "limit": "100"})
        priority = {"blocked": 0, "review": 1, "pending": 2}
        recommendations = [{"id": t["id"], "title": t["title"], "agent": t["agent"], "status": t["status"],
            "reason": t.get("blocker") or (t.get("result") or {}).get("summary") or "Waiting for the assigned agent",
            "evidence": (t.get("result") or {}).get("evidence", []), "opportunity_id": t.get("opportunity_id"),
            "conversation_id": t.get("conversation_id")} for t in sorted(tasks, key=lambda t:priority[t["status"]])]
        return {"ready": True, "connections": connections,
                "workflows": self.db.rows("client_finder_workflows", {"order": "name.asc"}),
                "operations": self.db.rows("client_finder_operations", {"order": "created_at.desc", "limit": "50"}),
                "jobs": jobs, "job_total": self.db.count("client_finder_jobs"),
                "resources": self.db.rows("client_finder_resources", {"order": "title.asc", "limit": "100"}),
                "meetings": self.db.rows("client_finder_meetings", {"order": "starts_at.desc.nullslast", "limit": "100"}),
                "imports": self.db.rows("client_finder_import_batches", {"order": "created_at.desc", "limit": "25"}, select="id,provider,resource_id,status,summary,created_at,committed_at,digest"),
                "drafts": self.db.rows("client_finder_messages", {"kind": "neq.reply", "order": "updated_at.desc", "limit": "100"}),
                "uncertain_outreach_attempts": self.db.rows("client_finder_send_attempts", {"send_class":"eq.outreach","status":"eq.send_unknown","rfc_message_id":"not.is.null","limit":"50"},select="id,message_id,subject"),
                "recommendations": recommendations,
                "crm_links": self.db.rows("client_finder_crm_links", {"limit": "100"}),
                "controls": self.db.rows("client_finder_settings", {"id": "eq.1"}, select="sending_enabled,application_daily_limit,applications_enabled,legacy_queue_reconciled_at,application_worker_verified_at,application_policy_verified_at")[0],
                "budget": self.db.rpc("client_finder_acquisition_usage", {}),
                "drafting": {"model_configured": bool(os.environ.get("OPENROUTER_API_KEY"))}, "page_limit": 100}

    def jobs(self, after_id=None):
        query = {"order":"id.asc","limit":"101"}
        if after_id:
            query["id"]="gt."+_id(after_id)
        rows=self.db.rows("client_finder_jobs",query)
        return {"jobs":rows[:100],"next_after":rows[99]["id"] if len(rows)>100 else None}

    def job(self, job_id):
        rows = self.db.rows("client_finder_jobs", {"id": "eq."+_id(job_id)})
        if not rows:
            raise ValueError("Job not found")
        j = rows[0]
        drafts = self.db.rows("client_finder_messages", {"job_id": "eq."+j["id"]})
        for d in drafts:
            d["blocker"] = self.db.rpc("client_finder_application_block", {"message_id": d["id"], "delivery": True})
        return {"job": j, "draft": drafts[0] if drafts else None,
                "drafting": {"model_configured": bool(os.environ.get("OPENROUTER_API_KEY"))},
                "conversation_options": self.db.rows("client_finder_conversations", {"order":"last_message_at.desc.nullslast","limit":"100"}, select="id,subject,opportunity_id,category,reply_email"),
                "linked_conversations": self.db.rows("client_finder_conversations", {"opportunity_id":"eq."+j["opportunity_id"]}, select="id,subject,opportunity_id,category,reply_email"),
                "tasks": self.db.rows("client_finder_tasks", {"opportunity_id": "eq."+j["opportunity_id"], "order": "created_at.desc", "limit": "50"}),
                "history": self.db.rows("client_finder_history", {"opportunity_id": "eq."+j["opportunity_id"], "limit": "50"}),
                "attempts": self.db.rows("client_finder_send_attempts", {"message_id": "eq."+drafts[0]["id"]}) if drafts else []}

    def preview(self, data):
        provider = data.get("provider")
        if provider not in ("sheets", "notion", "manual"):
            raise ValueError("Select a supported history source")
        resource = text(data.get("resource_id", ""), 500, True)
        records = data.get("records")
        if not isinstance(records, list) or not 1<=len(records)<=100:
            raise ValueError("Import 1–100 records per preview")
        normalized, seen, conflicts, duplicates = [], set(), [], 0
        for index, row in enumerate(records):
            if not isinstance(row, dict):
                raise ValueError(f"Record {index+1} must be an object")
            if row.get("kind", "job") == "job":
                rec = normalize_job({**row,"source_confirmed":False})
                rec["external_id"] = text(str(row.get("external_id") or rec["job_key"]), 500, True)
            elif row.get("kind") == "client":
                rec = {"kind": "client", "external_id": text(row.get("external_id", ""), 500, True),
                       "lead_id": _id(row["lead_id"]) if row.get("lead_id") else None,
                       "title": text(row.get("title", ""), 500, True)}
            else:
                raise ValueError(f"Unsupported record kind at row {index+1}")
            rec["sent_body"] = text(row.get("sent_body", ""), 20000)
            rec["draft_body"] = text(row.get("draft_body", ""), 20000)
            rec["content_evidence"] = "recorded_sent_body" if rec["sent_body"] else "historical_draft_only" if rec["draft_body"] else "no_message_content"
            email = text(row.get("suppressed_email", ""), 254).lower()
            if email and not business_email(email):
                raise ValueError("Invalid suppression address")
            if email:
                rec["suppressed_email"] = email
            if rec["external_id"] in seen:
                raise ValueError("Duplicate external reference within import")
            seen.add(rec["external_id"])
            prior = self.db.rows("client_finder_history", {"provider": "eq."+provider,"resource_id": "eq."+resource,"external_id": "eq."+rec["external_id"]})
            if prior:
                if fingerprint(prior[0]["original"]) != fingerprint(rec):
                    conflicts.append(rec["external_id"])
                else:
                    duplicates += 1
            normalized.append(rec)
        summary = {"records": len(normalized), "duplicates": duplicates, "new": len(normalized)-duplicates-len(conflicts), "conflicts": conflicts,
                   "notice": "Original trackers stay unchanged. Matching jobs retain their current content and outcomes; reported past submissions stop repeat applications. Historical content never grants approval."}
        return self.command("import_preview", {"provider": provider, "resource_id": resource, "records": normalized,
                    "digest": fingerprint(normalized), "summary": summary})

    def action(self, path, data):
        if path == "/api/acquisition/jobs":
            return self.db.rpc("client_finder_job_upsert", {"item": normalize_job(data), "actor": self.actor})
        if path == "/api/acquisition/job-stage":
            return self.db.rpc("client_finder_job_stage", {"job_id": _id(data["job_id"]), "status": data["status"], "note": text(data.get("note", "")), "actor": self.actor})
        if path == "/api/acquisition/job-conversation":
            return self.db.rpc("client_finder_link_job_conversation", {"job_id":_id(data["job_id"]),"conversation_id":_id(data["conversation_id"]),
                "expected_opportunity_id":_id(data["expected_opportunity_id"]) if data.get("expected_opportunity_id") else None,"actor":self.actor})
        if path == "/api/acquisition/resources":
            resource=normalize_resource(data)
            if resource["kind"]=="proof":
                if not resource["url"]:
                    raise ValueError("A reviewed proof link is required")
                from .research import SafeSiteFetcher, ResearchError
                try:
                    SafeSiteFetcher().fetch(resource["url"])
                except ResearchError:
                    raise ValueError("Proof link could not be verified. Keep it out of approved drafts until reviewed.") from None
            return self.command("resource", resource)
        if path == "/api/acquisition/import-preview":
            return self.preview(data)
        if path == "/api/acquisition/import-fetch":
            from .integrations import fetch_history
            provider, resource = data["provider"], text(data["resource_id"],500,True)
            return self.preview({"provider":provider,"resource_id":resource,"records":fetch_history(self.db,provider,resource)})
        if path == "/api/acquisition/import-commit":
            return self.command("import_commit", {"batch_id": _id(data["batch_id"]), "digest": text(data["digest"],64,True)})
        if path == "/api/acquisition/queue":
            return self.command("queue", {"kind": data["kind"], "request_id": _id(data["request_id"])})
        if path == "/api/acquisition/operation":
            return self.command("operation_action", {"id": _id(data["id"]), "action": data["action"]})
        if path == "/api/acquisition/select-connection":
            from .integrations import validate_selection
            return self.command("select_connection", {"provider": data["provider"], "selected": validate_selection(data["provider"],data["selected"])})
        if path == "/api/acquisition/pause":
            return self.command("pause", {"provider": data["provider"]})
        if path == "/api/acquisition/link-meeting":
            return self.command("link_meeting", {"meeting_id": _id(data["meeting_id"]), "opportunity_id": _id(data["opportunity_id"])})
        if path == "/api/acquisition/application-save":
            revision = data.get("expected_revision")
            if type(revision) is not int or revision<0:
                raise ValueError("Expected revision required")
            resources = []
            ids = data.get("resource_ids", [])
            if not isinstance(ids, list) or len(ids)>12 or len(set(ids))!=len(ids):
                raise ValueError("Choose at most 12 distinct reviewed resources")
            for rid in ids:
                rows = self.db.rows("client_finder_resources", {"id": "eq."+_id(rid),"active": "eq.true","verified_at": "not.is.null"})
                if not rows:
                    raise ValueError("Resource is missing or unverified")
                r = rows[0]
                resources.append({k:r.get(k) for k in ("id","title","kind","url","version")})
            answers = data.get("answers", [])
            if not isinstance(answers,list) or len(answers)>25:
                raise ValueError("Invalid screening answers")
            answers = [{"question":text(a["question"],1000,True),"answer":text(a["answer"],4000)} for a in answers]
            from .applications import submission_text
            letter = text(data["body"],20000,True)
            payload = {"answers":answers,"resources":resources,"apply_points":1,"delivery":data.get("delivery","manual"),"letter_body":letter}
            exact = submission_text(letter,answers,resources)
            return self.db.rpc("client_finder_application_save", {"job_id":_id(data["job_id"]),"expected_revision":revision,
                "subject":text(data["subject"],998,True),"body":text(exact,20000,True),"payload":payload,"actor":self.actor})
        if path == "/api/acquisition/application-approve":
            if type(data.get("revision")) is not int or data["revision"]<1:
                raise ValueError("Exact revision required")
            return self.db.rpc("client_finder_application_approve", {"message_id":_id(data["message_id"]),"revision":data["revision"],"via":"web","actor":self.actor})
        if path == "/api/acquisition/manual-result":
            return self.db.rpc("client_finder_application_manual_result", {"attempt_id":_id(data["attempt_id"]),"reference":safe_url(data["reference"]),"actor":self.actor})
        if path == "/api/acquisition/manual-handoff":
            from .applications import verify_resources
            attempt_id=_id(data["attempt_id"])
            rows=self.db.rows("client_finder_send_attempts",{"id":"eq."+attempt_id,"send_class":"eq.application","status":"eq.claimed"})
            if not rows: raise ValueError("Approved application required")
            verify_resources(self.db,rows[0])
            return self.db.rpc("client_finder_application_handoff",{"attempt_id":attempt_id,"actor":self.actor})
        if path == "/api/acquisition/application-reconcile":
            from .applications import reconcile_application
            return reconcile_application(self.db,_id(data["attempt_id"]))
        if path == "/api/acquisition/outreach":
            if type(data.get("revision")) is not int or data["revision"]<1:
                raise ValueError("Exact revision required")
            return self.db.rpc("client_finder_outreach_review", {"message_id":_id(data["message_id"]),"revision":data["revision"],"action":data["action"],
                "subject":text(data.get("subject",""),998),"body":text(data.get("body",""),20000),"actor":self.actor})
        if path == "/api/acquisition/outreach-reconcile":
            from .replies import reconcile_reply
            return reconcile_reply(self.db,_id(data["attempt_id"]),_outreach=True)
        if path == "/api/acquisition/crm-link":
            from .integrations import bind_crm
            return bind_crm(self.db,self.actor,data)
        if path == "/api/acquisition/crm-resolve":
            return self.db.rpc("client_finder_crm_action", {"operation":"resolve","item":{"opportunity_id":_id(data["opportunity_id"]),"decision":data["decision"]},"actor":self.actor})
        if path == "/api/acquisition/crm-reconcile":
            from .integrations import reconcile_crm
            return reconcile_crm(self.db,_id(data["operation_id"]))
        raise ValueError("Unknown acquisition action")


def intake_jobs(database, data):
    """Adapter for the existing Dustin workflow. Source payload cannot grant authority."""
    import os
    from .research import SafeSiteFetcher, ResearchError
    if data.get("workflow_id") != "V0xHCzfFMgKR61yh" or not isinstance(data.get("jobs"),list) or not 1<=len(data["jobs"])<=10:
        raise ValueError("Bounded Dustin job intake required")
    con=database.rows("client_finder_connections",{"provider":"eq.n8n"})
    if not con or con[0]["status"]!="verified" or not con[0]["enabled"]:
        raise ValueError("Verify the personal n8n source before intake")
    actor=_id(os.environ["CLIENT_FINDER_OWNER_AUTH_ID"])
    results=[]; fetcher=SafeSiteFetcher()
    # Failures return an error; retrying the complete batch is safe by job_key.
    for item in data["jobs"]:
        item={**item,"source_confirmed":False,"applied_at":None,"status":"new"}
        job=normalize_job(item)
        if job["platform"]!="onlinejobs":
            raise ValueError("Dustin intake only accepts OnlineJobs references")
        try:
            page=fetcher.fetch(job["source_url"])
            observed=" ".join(page.text.split())
            job["source_confirmed"]=" ".join(job["description"].split()) in observed
        except ResearchError:
            pass
        if not job["source_confirmed"]:
            job["blockers"].append("Open the original posting and verify its description before qualification")
        results.append(database.rpc("client_finder_job_upsert",{"item":job,"actor":actor})["id"])
    return {"status":"ingested","job_ids":results}
