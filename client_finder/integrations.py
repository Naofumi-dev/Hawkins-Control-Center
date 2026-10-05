"""Selected personal integrations. Fixed destinations, bounded reads, no credential discovery."""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

from .acquisition import WORKFLOWS, fingerprint, text
from .gmail import Gmail, GmailError, OWNER_EMAIL, request_json
from .providers import ProviderConfigurationError, ProviderError, _json_request

N8N = "https://n8n.armageddonvivas.cloud"
GHL = "https://services.leadconnectorhq.com"
SELECTIONS = {
    "google": {"calendar_ids", "file_ids", "sheet_ids"}, "notion": {"data_source_ids", "bot_id"},
    "n8n": {"project_id", "project_ids"}, "telegram": set(), "onlinejobs": set(), "loom": set(),
    "calcom": {"event_type_ids"}, "fathom": {"recording_ids"},
    "ghl": {"location_id", "pipeline_id", "stage_map", "outbound_automation_review"},
}


def validate_selection(provider, selected):
    if provider not in SELECTIONS or not isinstance(selected, dict) or set(selected)-SELECTIONS[provider]:
        raise ValueError("Unsupported personal resource selection")
    result = {}
    for key, value in selected.items():
        if key.endswith("_ids"):
            if not isinstance(value, list) or len(value)>20:
                raise ValueError("Select at most 20 resources")
            result[key] = [text(str(v), 254, True) for v in value]
        elif key == "stage_map":
            if not isinstance(value, dict) or set(value)-{"new","qualified","loom_call","proposal_offer","won","lost","onboarding"}:
                raise ValueError("Invalid personal pipeline mapping")
            result[key] = {k:text(v,100,True) for k,v in value.items()}
        else:
            result[key] = text(value, 2000, True)
    return result


def credential(name):
    value = os.environ.get(name, "")
    if not value:
        raise ProviderConfigurationError("Personal integration credential missing")
    return value


def personal(email):
    if str(email or "").lower() != OWNER_EMAIL:
        raise ProviderConfigurationError("Wrong personal account")
    return OWNER_EMAIL


def notion_headers():
    return {"Authorization":"Bearer "+credential("HAWKINS_NOTION_TOKEN"),"Notion-Version":"2025-09-03"}


def verify_notion(selected):
    headers = notion_headers()
    me = request_json("https://api.notion.com/v1/users/me",headers=headers)
    if me.get("id") != selected.get("bot_id"):
        raise ProviderConfigurationError("Wrong Notion integration")
    email = me.get("person",{}).get("email") or me.get("bot",{}).get("owner",{}).get("user",{}).get("person",{}).get("email")
    personal(email)
    return headers


def ghl_connection(db):
    rows = db.rows("client_finder_connections", {"provider":"eq.ghl"})
    if not rows or rows[0]["status"] == "paused":
        raise ProviderConfigurationError("Personal CRM connection unavailable")
    selected = rows[0]["selected"]
    location, pipeline = selected.get("location_id"), selected.get("pipeline_id")
    if not location or not pipeline:
        raise ProviderConfigurationError("Select one personal GHL location and pipeline")
    headers = {"Authorization":"Bearer "+credential("HAWKINS_GHL_TOKEN"),"Version":"2021-07-28"}
    result = request_json(GHL+"/locations/"+quote(location,safe=""), headers=headers).get("location",{})
    if result.get("id") != location:
        raise ProviderConfigurationError("Wrong CRM location")
    personal(result.get("email"))
    pipelines = request_json(GHL+"/opportunities/pipelines?"+urlencode({"locationId":location}),headers=headers).get("pipelines",[])
    chosen = next((p for p in pipelines if p.get("id")==pipeline),None)
    if not chosen:
        raise ProviderConfigurationError("Personal pipeline was not found")
    stages = {s["id"] for s in chosen.get("stages",[])}
    if any(v not in stages for v in selected.get("stage_map",{}).values()):
        raise ProviderConfigurationError("Personal pipeline stage mapping changed")
    return selected, headers


class IntegrationSync:
    def __init__(self,database):
        self.db = database

    def run(self,provider):
        connection = self.db.rpc("client_finder_integration_record",{"operation":"claim","item":{"provider":provider}})
        base = {"provider":provider,"lease_id":connection["lease_id"],"identity":OWNER_EMAIL}
        def record(op, item):
            return self.db.rpc("client_finder_integration_record",{"operation":op,"item":{**base,**item}})
        try:
            selected = validate_selection(provider,connection["selected"])
            checkpoint = connection.get("checkpoint",{})
            if provider == "google":
                checkpoint = self.google(selected,checkpoint,record)
            elif provider == "n8n":
                base["identity"]=self.n8n(selected,record)
            elif provider == "calcom":
                self.calcom(selected,record)
            elif provider == "fathom":
                self.fathom(selected,record)
            elif provider == "ghl":
                ghl_connection(self.db)
            elif provider == "notion":
                verify_notion(selected)
            elif provider == "telegram":
                from .telegram_replies import ReplyTelegram
                me=ReplyTelegram(self.db).verify()
                base["identity"]="@"+str(me.get("username") or me["id"])
            elif provider == "onlinejobs":
                from .onlinejobs_browser import PersonalOnlineJobs
                browser=PersonalOnlineJobs()
                try: browser.verify()
                finally: browser.close()
            else:
                raise ProviderConfigurationError("Reviewed links or a verified platform worker are required")
            record("complete",{"identity":base["identity"],"checkpoint":checkpoint})
            return {"provider":provider,"status":"verified"}
        except Exception as exc:
            code = "personal_setup_or_identity_check_failed" if isinstance(exc,ProviderConfigurationError) else "sync_failed_checkpoint_retained"
            record("failure",{"error_code":code})
            return {"provider":provider,"status":"blocked","error_code":code}

    def google(self,selected,checkpoint,record):
        gmail = Gmail.from_environment()
        gmail.verify()  # Identity must be checked before any Drive/Sheets/Calendar data.
        next_checkpoint = dict(checkpoint)
        for file_id in selected.get("file_ids",[]):
            f = request_json("https://www.googleapis.com/drive/v3/files/"+quote(file_id,safe="")+"?"+urlencode({
                "fields":"id,name,version,modifiedTime,webViewLink,trashed,owners(emailAddress)"}),headers=gmail.headers)
            if not any(o.get("emailAddress","").lower()==OWNER_EMAIL for o in f.get("owners",[])):
                raise ProviderConfigurationError("Selected Drive file is not personally owned")
            record("resource_version",{"external_id":file_id,"provider_version":str(f.get("version",f.get("modifiedTime",""))),"trashed":f.get("trashed",False)})
        for cal in selected.get("calendar_ids",[]):
            own = request_json("https://www.googleapis.com/calendar/v3/users/me/calendarList/"+quote(cal,safe=""),headers=gmail.headers)
            if own.get("accessRole") != "owner":
                raise ProviderConfigurationError("Selected calendar is not personally owned")
            token = checkpoint.get(cal)
            events, new_token, reset = self.calendar_events(gmail.headers,cal,token)
            for e in events:
                record("meeting",{"identity":OWNER_EMAIL,"external_id":cal+":"+e["id"],"correlation_key":e.get("iCalUID"),
                    "title":str(e.get("summary") or "Calendar meeting")[:500],"starts_at":e.get("start",{}).get("dateTime"),
                    "status":e.get("status","confirmed"),"summary":"","version":str(e.get("etag") or e.get("updated") or e["id"])})
            # Resets alter only the calendar projection, never business history/tasks.
            if reset:
                record("calendar_snapshot",{"calendar_id":cal,"event_ids":[cal+":"+e["id"] for e in events]})
            next_checkpoint[cal] = new_token
        return next_checkpoint

    def calendar_events(self,headers,cal,token):
        base = "https://www.googleapis.com/calendar/v3/calendars/"+quote(cal,safe="")+"/events"
        rows, page, seen = [], None, set()
        for _ in range(100):
            params = {"maxResults":250,"singleEvents":"true","showDeleted":"true"}
            if token:
                params["syncToken"] = token
            if page:
                params["pageToken"] = page
            try:
                result = request_json(base+"?"+urlencode(params),headers=headers)
            except GmailError as exc:
                if exc.status == 410 and token:
                    return self.calendar_events(headers,cal,None)
                raise
            rows.extend(result.get("items",[]))
            page = result.get("nextPageToken")
            if not page:
                if not result.get("nextSyncToken"):
                    raise ProviderError("Calendar checkpoint missing")
                return rows, result["nextSyncToken"], not bool(token)
            if page in seen:
                raise ProviderError("Repeated calendar page")
            seen.add(page)
        raise ProviderError("Calendar page limit reached; checkpoint retained")

    def n8n(self,selected,record):
        projects = selected.get("project_ids") or ([selected["project_id"]] if selected.get("project_id") else [])
        if not projects:
            raise ProviderConfigurationError("Select the personal n8n project")
        headers = {"X-N8N-API-KEY":credential("HAWKINS_N8N_API_KEY")}
        expected=credential("HAWKINS_N8N_OWNER_EMAIL").strip().lower()
        for project in projects:
            identity = request_json(N8N+"/api/v1/projects/"+quote(project,safe=""),headers=headers)
            owner = identity.get("owner",{}).get("email")
            if not owner:
                members=request_json(N8N+"/api/v1/projects/"+quote(project,safe="")+"/users?limit=100",headers=headers)
                if members.get("nextCursor"):
                    raise ProviderConfigurationError("Personal project membership needs review")
                owners=[m for m in members.get("data",[]) if m.get("role") in ('project:personalOwner','project:admin','project:owner')]
                owner=next((m.get("email") or m.get("user",{}).get("email") for m in owners if (m.get("email") or m.get("user",{}).get("email","")).lower()==expected),None)
            if not expected or str(owner or '').lower()!=expected:
                raise ProviderConfigurationError("Wrong personal n8n project owner")
        for wid,_,_ in WORKFLOWS:
            wf = request_json(N8N+"/api/v1/workflows/"+wid,headers=headers)
            refs = [s.get("projectId") or s.get("project",{}).get("id") for s in wf.get("shared",[])]
            if wf.get("projectId") not in projects and not set(projects).intersection(refs):
                raise ProviderConfigurationError("Workflow personal project could not be verified")
            history = request_json(N8N+"/api/v1/executions?"+urlencode({"workflowId":wid,"limit":20,"includeData":"false"}),headers=headers)
            runs = [{"id":str(x["id"]),"status":x["status"],"started_at":x.get("startedAt"),"finished_at":x.get("stoppedAt")} for x in history.get("data",[]) if str(x.get("workflowId"))==wid]
            record("workflow",{"id":wid,"active":wf.get("active") is True,"runs":runs})
        return expected

    def calcom(self,selected,record):
        headers = {"Authorization":"Bearer "+credential("HAWKINS_CALCOM_TOKEN"),"cal-api-version":"2026-05-01"}
        personal(request_json("https://api.cal.com/v2/me",headers=headers).get("data",{}).get("email"))
        chosen = selected.get("event_type_ids",[])
        if not chosen:
            raise ProviderConfigurationError("Select personal acquisition event types")
        cursor,seen=None,set()
        for _ in range(50):
            params={"limit":100,"eventTypeIds":",".join(chosen)}
            if cursor: params["cursor"]=cursor
            result = request_json("https://api.cal.com/v2/bookings?"+urlencode(params),headers=headers)
            rows = result.get("data",[])
            if not isinstance(rows,list):
                raise ProviderError("Unexpected booking response")
            for b in rows:
                if str(b.get("eventTypeId",b.get("eventType",{}).get("id"))) not in chosen:
                    continue
                if not any(h.get("email","").lower()==OWNER_EMAIL for h in b.get("hosts",[])):
                    raise ProviderConfigurationError("Booking belongs to another host")
                record("meeting",{"external_id":b["uid"],"correlation_key":b.get("icsUid"),"title":b["title"],"starts_at":b.get("start"),
                    "status":b["status"],"summary":"","version":fingerprint([b.get("start"),b.get("end"),b["status"]])})
            page=result.get("pagination",{})
            if page.get("hasMore") is False:
                return
            cursor=page.get("nextCursor")
            if not cursor or cursor in seen:
                raise ProviderError("Booking pagination incomplete")
            seen.add(cursor)
        raise ProviderError("Booking pagination incomplete")

    def fathom(self,selected,record):
        ids = selected.get("recording_ids",[])
        if not ids:
            raise ProviderConfigurationError("Select acquisition recordings")
        headers = {"X-Api-Key":credential("HAWKINS_FATHOM_API_KEY")}
        cursor, seen, found = None,set(),set()
        for _ in range(50):
            params = {"recorded_by[]":OWNER_EMAIL,"include_transcript":"false","include_summary":"true","include_action_items":"true"}
            if cursor:
                params["cursor"]=cursor
            result = request_json("https://api.fathom.ai/external/v1/meetings?"+urlencode(params),headers=headers)
            for m in result.get("items",[]):
                personal(m.get("recorded_by",{}).get("email"))
                mid = str(m.get("recording_id",""))
                if mid not in ids:
                    continue
                found.add(mid)
                summary = m.get("default_summary") or {}
                body = summary.get("markdown_formatted","") if isinstance(summary,dict) else str(summary)
                record("meeting",{"external_id":mid,"correlation_key":None,"title":m.get("title") or "Selected call",
                    "starts_at":m.get("scheduled_start_time") or m.get("recording_start_time"),"status":"recorded",
                    "summary":body[:12000],"action_items":m.get("action_items",[])[:30],"version":fingerprint([body,m.get("action_items",[])])})
            cursor = result.get("next_cursor")
            if not cursor:
                if found!=set(ids):
                    raise ProviderError("Some selected recordings were not found")
                return
            if cursor in seen:
                raise ProviderError("Repeated Fathom cursor")
            seen.add(cursor)
        raise ProviderError("Fathom pagination incomplete")


def fetch_history(database,provider,resource_id):
    """Read selected trackers only; return rows for a persisted import preview, never commit."""
    key = "google" if provider=="sheets" else "notion"
    rows = database.rows("client_finder_connections",{"provider":"eq."+key})
    if not rows or rows[0]["status"]=="paused":
        raise ProviderConfigurationError("Select a personal history source")
    selected = rows[0]["selected"]
    if provider=="sheets":
        if resource_id not in selected.get("sheet_ids",[]):
            raise ValueError("Sheet is not selected")
        gmail=Gmail.from_environment(); gmail.verify()
        # Match the source spreadsheet before reading values. All row data stays server-side.
        f=request_json("https://www.googleapis.com/drive/v3/files/"+quote(resource_id,safe="")+"?fields=id,owners(emailAddress)",headers=gmail.headers)
        if not any(o.get("emailAddress","").lower()==OWNER_EMAIL for o in f.get("owners",[])):
            raise ProviderConfigurationError("Wrong spreadsheet owner")
        values=request_json("https://sheets.googleapis.com/v4/spreadsheets/"+quote(resource_id,safe="")+"/values/Leads!A1:AZ102",headers=gmail.headers).get("values",[])
        if not values:
            raise ValueError("Selected Leads sheet is empty")
        if len(values)>101:
            raise ValueError("Export the selected history in batches of 100; source was not partially imported")
        names=[re.sub(r"\W+","_",v.strip().lower()).strip("_") for v in values[0]]
        if len(set(names))!=len(names):
            raise ValueError("Duplicate spreadsheet column labels")
        return [dict(zip(names,row)) for row in values[1:]]
    if provider=="notion":
        if resource_id not in selected.get("data_source_ids",[]):
            raise ValueError("Notion source is not selected")
        headers=verify_notion(selected)
        result=request_json("https://api.notion.com/v1/data_sources/"+quote(resource_id,safe="")+"/query",headers=headers,payload={"page_size":100})
        if result.get("has_more"):
            raise ValueError("Use a selected export split into batches of 100; no partial source import")
        records=[]
        for page in result.get("results",[]):
            row={"external_id":page["id"]}
            for name,p in page.get("properties",{}).items():
                typ=p.get("type"); value=p.get(typ)
                if typ in ("title","rich_text"):
                    value="".join(v.get("plain_text","") for v in value or [])
                elif typ=="date":
                    value=(value or {}).get("start")
                elif typ in ("select","status"):
                    value=(value or {}).get("name")
                if isinstance(value,(str,bool,int,float)):
                    row[re.sub(r"\W+","_",name.lower()).strip("_")]=value
            records.append(row)
        return records
    raise ValueError("Unsupported history provider")


def bind_crm(database,actor,data):
    from .control_center import _id
    selected,headers=ghl_connection(database)
    remote=text(data.get("remote_id",""),100,True)
    record=request_json(GHL+"/opportunities/"+quote(remote,safe=""),headers=headers).get("opportunity",{})
    if record.get("locationId")!=selected["location_id"] or record.get("pipelineId")!=selected["pipeline_id"]:
        raise ProviderConfigurationError("Opportunity is outside the personal pipeline")
    return database.rpc("client_finder_crm_action",{"operation":"bind","actor":actor,"item":{
        "opportunity_id":_id(data["opportunity_id"]),"remote_id":remote,"remote_stage":record["pipelineStageId"],
        "location_id":selected["location_id"],"pipeline_id":selected["pipeline_id"]}})


def mirror_stage(database,operation):
    selected,headers=ghl_connection(database)
    if not selected.get("outbound_automation_review"):
        raise ProviderConfigurationError("Review pipeline automations before mirroring")
    item=operation["payload"]
    record=request_json(GHL+"/opportunities/"+quote(item["remote_id"],safe=""),headers=headers).get("opportunity",{})
    if record.get("locationId")!=selected["location_id"] or record.get("pipelineId")!=selected["pipeline_id"]:
        raise ProviderConfigurationError("Wrong CRM resource")
    if record.get("pipelineStageId")==item["target_stage"]:
        return database.rpc("client_finder_crm_result",{"operation_id":operation["id"],"remote_stage":item["target_stage"],"outcome":"confirmed"})
    if record.get("pipelineStageId")!=item["expected_stage"]:
        return database.rpc("client_finder_crm_result",{"operation_id":operation["id"],"remote_stage":record.get("pipelineStageId"),"outcome":"conflict"})
    # Atomically recheck current local stage, selected pipeline and operation before the PUT.
    payload=database.rpc("client_finder_crm_begin",{"operation_id":operation["id"],"lease_id":operation["lease_id"]})
    if not payload:
        return {"status":"stale"}
    try:
        result=_json_request(GHL+"/opportunities/"+quote(item["remote_id"],safe=""),method="PUT",headers=headers,payload={"pipelineStageId":item["target_stage"]})
        if result.get("opportunity",{}).get("pipelineStageId")!=item["target_stage"]:
            raise ProviderError("CRM update unconfirmed")
    except Exception:
        return database.rpc("client_finder_crm_result",{"operation_id":operation["id"],"remote_stage":None,"outcome":"unknown"})
    return database.rpc("client_finder_crm_result",{"operation_id":operation["id"],"remote_stage":item["target_stage"],"outcome":"confirmed"})


def run_operation(database):
    op=database.rpc("client_finder_operation_worker",{"operation":"claim","item":{}})
    if not op:
        return {"status":"idle"}
    result,error=None,None
    try:
        if op["kind"]=="discover":
            from .server import build_runner
            result=build_runner().run(limit=5).json()
        elif op["kind"]=="inbox_sync":
            from .inbox import InboxSync
            result=InboxSync(Gmail.from_environment(),database).run()
        elif op["kind"]=="agent_run":
            from .agents import TaskRunner
            result=TaskRunner(database).run_one()
        elif op["kind"]=="integrations_sync":
            connections=database.rows("client_finder_connections",{})
            result={"connections":[IntegrationSync(database).run(c["provider"]) for c in connections if c["status"]!="paused" and (c.get("selected") or c["provider"] in ('telegram','onlinejobs')) and c["provider"]!='loom']}
            if any(c["status"]=="blocked" for c in result["connections"]):
                error="one_or_more_connections_need_setup"
        elif op["kind"]=="ghl_mirror":
            return mirror_stage(database,op)
    except Exception:
        error="operation_failed_check_personal_setup_and_budget"
    return database.rpc("client_finder_operation_worker",{"operation":"finish","item":{"id":op["id"],"lease_id":op["lease_id"],"result":result,"error_code":error}})


def reconcile_crm(database,operation_id):
    rows=database.rows("client_finder_operations",{"id":"eq."+operation_id,"kind":"eq.ghl_mirror","status":"eq.needs_checking"})
    if not rows:
        raise ValueError("Uncertain CRM operation required")
    op=rows[0]; selected,headers=ghl_connection(database); item=op["payload"]
    remote=request_json(GHL+"/opportunities/"+quote(item["remote_id"],safe=""),headers=headers).get("opportunity",{})
    if remote.get("locationId")!=selected["location_id"] or remote.get("pipelineId")!=selected["pipeline_id"]:
        raise ProviderConfigurationError("Wrong CRM resource")
    stage=remote.get("pipelineStageId")
    if not stage:
        raise ProviderError("Remote stage could not be verified")
    return database.rpc("client_finder_crm_result",{"operation_id":op["id"],"remote_stage":stage,"outcome":"confirmed" if stage==item["target_stage"] else "conflict"})
