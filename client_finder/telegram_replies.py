"""Dedicated-bot review for the exact same revision shown in the web app."""
import os
import re
import uuid

from .gmail import request_json
from .providers import ProviderConfigurationError, ProviderError


class ReplyTelegram:
    def __init__(self, database):
        self.db = database
        self.token = os.environ.get("CLIENT_FINDER_TELEGRAM_TOKEN", "")
        self.bot_id = os.environ.get("CLIENT_FINDER_TELEGRAM_BOT_ID", "")
        if not self.token or not self.bot_id.isdigit():
            raise ProviderConfigurationError("Dedicated client-outreach bot setup incomplete")
        rows = database.rows("client_finder_settings", {"id":"eq.1"}, select="owner_telegram_user_id,owner_telegram_chat_id")
        if not rows or not all(rows[0].values()):
            raise ProviderConfigurationError("Telegram owner setup incomplete")
        self.owner, self.chat = rows[0]["owner_telegram_user_id"], rows[0]["owner_telegram_chat_id"]

    def call(self, method, payload):
        if method not in ("getMe","sendMessage","answerCallbackQuery"):
            raise ValueError("Unsupported Telegram method")
        result = request_json("https://api.telegram.org/bot"+self.token+"/"+method, payload=payload)
        if not result.get("ok"):
            raise ProviderError("Dedicated bot request failed")
        return result.get("result")

    def verify(self):
        me = self.call("getMe", {})
        if not me or str(me.get("id")) != self.bot_id or me.get("is_bot") is not True:
            raise ProviderConfigurationError("Wrong Telegram bot")
        return me

    def publish_one(self):
        self.verify()
        rows = self.db.rows("client_finder_messages", {"kind":"eq.reply","status":"eq.pending_review","telegram_card_id":"is.null","order":"updated_at.asc","limit":"1"})
        if not rows:
            return {"status":"idle"}
        m=rows[0]
        conversations=self.db.rows("client_finder_conversations", {"id":"eq."+m["conversation_id"]})
        c=conversations[0]
        if c["context_version"] != m["context_version"]:
            return {"status":"stale_context"}
        label=f"DRAFT · Revision {m['revision']} · {m['id'][:8]}"
        intro=(f"{label}\nOpportunity: {c['subject']}\nSource: {c['acquisition_source']}\n"
               f"Evidence: {c['classification_reason']}\nOriginal: {c.get('platform_reference') or 'Personal Gmail thread'}\n"
               f"Proof: {m.get('reviewed_proof_url') or 'No proof selected'}\n\nTo: {m['recipient_email']}\nSubject: {m['subject']}\n\n{m['body']}")
        # All parts must have confirmed message IDs before any approval button is published.
        chunks=[intro[i:i+3000] for i in range(0,len(intro),3000)]
        for index,chunk in enumerate(chunks):
            result=self.call("sendMessage", {"chat_id":self.chat,"text":f"Part {index+1}/{len(chunks)}\n"+chunk,"link_preview_options":{"is_disabled":True}})
            if not result or not result.get("message_id"):
                raise ProviderError("Complete preview was not confirmed")
        key=uuid.UUID(m["id"]).hex+":"+str(m["revision"])
        result=self.call("sendMessage", {"chat_id":self.chat,"text":f"{label}\nRead all {len(chunks)} parts above. Approve only this exact revision.",
            "reply_markup":{"inline_keyboard":[[{"text":"Approve & send","callback_data":"ra:"+key},{"text":"Edit","callback_data":"re:"+key}],
                                                [{"text":"Skip","callback_data":"rs:"+key},{"text":"Do not contact","callback_data":"rd:"+key}]]}})
        if not result or not result.get("message_id"):
            raise ProviderError("Review buttons were not confirmed")
        self.db.rpc("client_finder_reply_bind_card", {"message_id":m["id"],"revision":m["revision"],"card_id":result["message_id"],"owner_user_id":self.owner,"chat_id":self.chat})
        return {"status":"review_published","message_id":m["id"],"revision":m["revision"]}

    def callback(self, payload):
        cb=payload.get("callback_query", {})
        sender=cb.get("from", {})
        message=cb.get("message", {})
        chat=message.get("chat", {})
        if sender.get("is_bot") or str(sender.get("id"))!=str(self.owner) or str(chat.get("id"))!=str(self.chat) or chat.get("type")!='private':
            return {"status":"ignored"}
        match=re.fullmatch(r"r([aesd]):([a-f0-9]{32}):([1-9][0-9]{0,5})",str(cb.get("data","")))
        if not match or not isinstance(message.get("message_id"),int):
            return {"status":"ignored"}
        self.verify()
        action,mid,revision=match.groups(); mid=str(uuid.UUID(mid)); revision=int(revision)
        if action=='a':
            self.db.rpc("client_finder_reply_approve", {"message_id":mid,"revision":revision,"via":"telegram","actor":"telegram:"+str(self.owner),
                "telegram_user_id":self.owner,"telegram_chat_id":self.chat,"telegram_card_id":message["message_id"]})
            notice="Approved and queued. Gmail acceptance is still pending."
        else:
            self.db.rpc("client_finder_reply_card_action", {"message_id":mid,"revision":revision,"action":{'e':'edit','s':'skip','d':'suppress'}[action],
                "card_id":message["message_id"],"owner_user_id":self.owner,"chat_id":self.chat})
            notice="Open Draft Studio to edit and save a new revision." if action=='e' else "Review action saved."
        self.call("answerCallbackQuery", {"callback_query_id":cb["id"],"text":notice})
        return {"status":"recorded"}
