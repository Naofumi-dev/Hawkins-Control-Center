"""Exact-revision application review and delivery. Unknown outcomes never retry."""
import re
import uuid

from .providers import ProviderConfigurationError, ProviderError
from .telegram_replies import ReplyTelegram


def verify_resources(database,attempt):
    from urllib.parse import quote
    from .gmail import Gmail,OWNER_EMAIL,request_json
    gmail=None
    for selected in attempt["application_payload"].get("resources",[]):
        rows=database.rows("client_finder_resources",{"id":"eq."+str(uuid.UUID(selected["id"]))})
        if not rows or not rows[0].get("active") or not rows[0].get("verified_at") or rows[0]["version"]!=selected["version"]:
            raise ProviderError("Reviewed resource changed")
        resource=rows[0]
        if resource["provider"]!="google":continue
        if gmail is None:
            gmail=Gmail.from_environment();gmail.verify()
        f=request_json("https://www.googleapis.com/drive/v3/files/"+quote(resource["external_id"],safe="")+"?fields=id,version,trashed,owners(emailAddress)",headers=gmail.headers)
        if f.get("trashed") or not any(o.get("emailAddress","").lower()==OWNER_EMAIL for o in f.get("owners",[])) or str(f.get("version",""))!=resource.get("metadata",{}).get("provider_version"):
            raise ProviderError("Selected Drive document changed or is not personally owned")


def submission_text(letter, answers, resources):
    parts=[letter.strip()]
    for a in answers:
        parts.append(a["question"].strip()+"\n"+a["answer"].strip())
    for r in resources:
        if r.get("url") and r.get("kind") in ("resume","proof","proposal"):
            parts.append(r["title"]+": "+r["url"])
    return "\n\n".join(parts)


def send_application(database,browser=None):
    database.rpc("client_finder_application_recover",{})
    rows=database.rows("client_finder_send_attempts",{"send_class":"eq.application","status":"eq.claimed","order":"claimed_at.asc","limit":"20"})
    attempt=next((a for a in rows if a["application_payload"]["delivery"]=="onlinejobs"),None)
    if not attempt:
        return {"status":"idle"}
    owned=browser is None
    started=False
    try:
        if owned:
            from .onlinejobs_browser import PersonalOnlineJobs
            browser=PersonalOnlineJobs()
        browser.verify()
        verify_resources(database,attempt)
        state=browser.inspect(attempt["application_payload"]["job_url"])
        if state["status"]!="open":
            database.rpc("client_finder_application_preflight",{"attempt_id":attempt["id"],"reason":"platform_"+state["status"]})
            return {"status":"blocked","reason":"platform_"+state["status"]}
        browser.prepare(attempt)
        # Only now, immediately before the final provider action, reserve delivery.
        approved=database.rpc("client_finder_application_begin",{"attempt_id":attempt["id"]})
        if not approved:
            return {"status":"canceled"}
        started=True
        browser.submit()
        state=browser.inspect(attempt["application_payload"]["job_url"])
        confirmed=state["status"]=="applied" and bool(state.get("reference"))
        result={"confirmed":confirmed,"reference":state.get("reference"),"job_key":attempt["application_payload"]["job_key"]}
        database.rpc("client_finder_application_result",{"attempt_id":attempt["id"],"result":result})
        return {"status":"confirmed" if confirmed else "needs_checking","attempt_id":attempt["id"]}
    except Exception:
        if started:
            database.rpc("client_finder_application_result",{"attempt_id":attempt["id"],"result":{"confirmed":False,"error":"provider_outcome_unconfirmed"}})
            return {"status":"needs_checking","attempt_id":attempt["id"]}
        database.rpc("client_finder_application_preflight",{"attempt_id":attempt["id"],"reason":"personal_session_or_form_needs_review"})
        return {"status":"blocked","attempt_id":attempt["id"]}
    finally:
        if owned and browser is not None:
            browser.close()


def reconcile_application(database,attempt_id,browser=None):
    rows=database.rows("client_finder_send_attempts",{"id":"eq."+str(uuid.UUID(attempt_id)),"send_class":"eq.application","status":"eq.send_unknown"})
    if not rows:
        raise ValueError("Unknown application attempt required")
    a=rows[0]
    if a["application_payload"]["delivery"]!="onlinejobs":
        return {"status":"manual_evidence_required"}
    owned=browser is None
    if owned:
        from .onlinejobs_browser import PersonalOnlineJobs
        browser=PersonalOnlineJobs()
    try:
        browser.verify()
        state=browser.inspect(a["application_payload"]["job_url"])
        if state["status"]!="applied" or not state.get("reference"):
            return {"status":"needs_checking"}
        # Existing application evidence only resolves this exact job attempt. Never submit here.
        return database.rpc("client_finder_application_result",{"attempt_id":a["id"],"result":{
            "confirmed":True,"reference":state["reference"],"job_key":a["application_payload"]["job_key"],"reconciled":True}})
    finally:
        if owned:
            browser.close()


class ApplicationTelegram(ReplyTelegram):
    def publish_one(self):
        self.verify()
        rows=self.db.rows("client_finder_messages",{"kind":"eq.application","status":"eq.pending_review","telegram_card_id":"is.null","order":"updated_at.asc","limit":"1"})
        if not rows:
            return {"status":"idle"}
        m=rows[0]; p=m["application_payload"]
        title=f"APPLICATION DRAFT · Revision {m['revision']} · {m['id'][:8]}"
        body=(f"{title}\nJob: {p['job_url']}\nDelivery: {p['delivery']}\nApply points: {p['apply_points']}\n"
              f"Subject: {m['subject']}\n\nExact submission:\n{m['body']}")
        chunks=[body[i:i+3000] for i in range(0,len(body),3000)]
        for i,chunk in enumerate(chunks):
            sent=self.call("sendMessage",{"chat_id":self.chat,"text":f"Part {i+1}/{len(chunks)}\n"+chunk,"link_preview_options":{"is_disabled":True}})
            if not sent or not sent.get("message_id"):
                raise ProviderError("Application preview incomplete")
        key=uuid.UUID(m["id"]).hex+":"+str(m["revision"])
        label="Approve & submit" if p["delivery"]=="onlinejobs" else "Approve manual handoff"
        sent=self.call("sendMessage",{"chat_id":self.chat,"text":title+"\nReview every part before approval.","reply_markup":{"inline_keyboard":[[
            {"text":label,"callback_data":"aa:"+key},{"text":"Edit","callback_data":"ae:"+key},{"text":"Skip","callback_data":"as:"+key}]]}})
        if not sent or not sent.get("message_id"):
            raise ProviderError("Application review card missing")
        self.db.rpc("client_finder_application_card",{"message_id":m["id"],"revision":m["revision"],"action":"bind","card_id":sent["message_id"],"owner_user_id":self.owner,"chat_id":self.chat})
        return {"status":"review_published","message_id":m["id"]}

    def callback(self,payload):
        cb=payload.get("callback_query",{}); sender=cb.get("from",{}); msg=cb.get("message",{}); chat=msg.get("chat",{})
        if sender.get("is_bot") or str(sender.get("id"))!=str(self.owner) or str(chat.get("id"))!=str(self.chat) or chat.get("type")!="private":
            return {"status":"ignored"}
        match=re.fullmatch(r"a([aes]):([a-f0-9]{32}):([1-9][0-9]{0,5})",str(cb.get("data","")))
        if not match or type(msg.get("message_id")) is not int:
            return {"status":"ignored"}
        self.verify()
        action,mid,rev=match.groups(); mid=str(uuid.UUID(mid)); rev=int(rev)
        if action=="a":
            self.db.rpc("client_finder_application_approve",{"message_id":mid,"revision":rev,"via":"telegram","actor":"telegram:"+str(self.owner),
                "telegram_user_id":self.owner,"telegram_chat_id":self.chat,"telegram_card_id":msg["message_id"]})
        else:
            self.db.rpc("client_finder_application_card",{"message_id":mid,"revision":rev,"action":"edit" if action=="e" else "skip","card_id":msg["message_id"],"owner_user_id":self.owner,"chat_id":self.chat})
        self.call("answerCallbackQuery",{"callback_query_id":cb["id"],"text":"Stored revision reviewed. Check Hawkins for the delivery result."})
        return {"status":"recorded"}
