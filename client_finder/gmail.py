"""Personal Gmail transport. Identity verification precedes every data operation."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from email.policy import SMTP

from .providers import ProviderError, ProviderConfigurationError, _NoRedirects

OWNER_EMAIL = "armageddonvivas@gmail.com"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailError(ProviderError):
    def __init__(self, status: int = 0):
        self.status = status
        super().__init__(f"Gmail request failed ({status or 'connection'})")


def request_json(url, *, headers=None, payload=None, form=None):
    data = None
    headers = dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    try:
        request = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.build_opener(_NoRedirects()).open(request, timeout=25) as response:
            raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ProviderError("Provider response too large")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ProviderError("Provider response is not an object")
            return result
    except urllib.error.HTTPError as exc:
        raise GmailError(exc.code) from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ProviderError("Provider request unavailable") from exc


class Gmail:
    def __init__(self, token: str):
        if not token:
            raise ProviderConfigurationError("Personal Gmail authorization required")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.verified = False

    @classmethod
    def from_environment(cls):
        values = {key: os.environ.get(key, "") for key in (
            "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")}
        if not all(values.values()):
            raise ProviderConfigurationError("Personal Gmail OAuth setup incomplete")
        result = request_json("https://oauth2.googleapis.com/token", form={
            "client_id": values["GOOGLE_CLIENT_ID"],
            "client_secret": values["GOOGLE_CLIENT_SECRET"],
            "refresh_token": values["GMAIL_REFRESH_TOKEN"], "grant_type": "refresh_token",
        })
        return cls(result.get("access_token", ""))

    def verify(self):
        self.verified = False
        result = request_json(GMAIL_API + "/profile", headers=self.headers)
        if result.get("emailAddress", "").lower() != OWNER_EMAIL:
            raise ProviderConfigurationError("Wrong Gmail account; no mailbox access permitted")
        if not str(result.get("historyId", "")).isdigit():
            raise ProviderError("Gmail history identity missing")
        self.verified = True
        return result

    def get(self, path, **query):
        if not self.verified:
            raise ProviderConfigurationError("Verify personal Gmail identity first")
        if not path.startswith(("/messages", "/history", "/threads")) or ".." in path:
            raise ValueError("Unsupported Gmail resource")
        suffix = "?" + urllib.parse.urlencode(query) if query else ""
        return request_json(GMAIL_API + path + suffix, headers=self.headers)

    def send(self, attempt, *, before_send=None):
        self.verify()
        # Recheck database authority after the last network identity check and
        # immediately before constructing/delivering the immutable payload.
        if before_send is not None:
            attempt = before_send()
            if not attempt:
                return {"canceled": True}
        msg = EmailMessage(policy=SMTP)
        msg["From"] = OWNER_EMAIL
        msg["To"] = attempt["recipient_email"]
        msg["Subject"] = attempt["subject"]
        # Deterministic RFC Message-ID is also the reconciliation key.
        msg["Message-ID"] = attempt["rfc_message_id"]
        if attempt.get("reply_thread_id"):
            msg["In-Reply-To"] = attempt["in_reply_to"]
            msg["References"] = attempt["references_header"]
        msg.set_content(attempt["body"])
        payload = {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}
        if attempt.get("reply_thread_id"):
            payload["threadId"] = attempt["reply_thread_id"]
        return request_json(GMAIL_API + "/messages/send", headers=self.headers, payload=payload)
