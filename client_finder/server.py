"""Internal discovery endpoint for Hawkins' hosted n8n scheduler."""

from __future__ import annotations

import hmac
import json
import os
import threading
import uuid
from pathlib import Path
from urllib.parse import urlsplit, unquote, parse_qs
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .discovery import DiscoveryRunner
from .cards import stored_card
from .followups import prepare_due_followups
from .mail import MailMonitor
from .providers import BraveSearch, ProviderError, SupabaseRest
from .control_center import ControlCenter, OwnerError, authenticate_owner
from .gmail import Gmail, OWNER_EMAIL
from .inbox import InboxSync
from .agents import TaskRunner
from .replies import send_one_reply, reconcile_reply
from .configuration import valid_api_key


DISCOVERY_LOCK = threading.Lock()
MAIL_POLL_LOCK = threading.Lock()
REQUIRED_CONFIGURATION = (
    "CLIENT_FINDER_SERVICE_TOKEN", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "BRAVE_SEARCH_API_KEY"
)


def build_runner() -> DiscoveryRunner:
    database = SupabaseRest(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])
    search = BraveSearch(os.environ["BRAVE_SEARCH_API_KEY"], database)
    return DiscoveryRunner(database, search)


def build_database() -> SupabaseRest:
    return SupabaseRest(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


class Handler(BaseHTTPRequestHandler):
    server_version = "HawkinsClientFinder/1.0"

    def _reply(self, status: HTTPStatus, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        # Request paths may contain private conversation identifiers. No payload/access logs.
        pass

    def _owner_api(self, payload=None):
        database = build_database()
        actor = authenticate_owner(self.headers.get("Authorization", ""), database)
        api = ControlCenter(database, actor)
        path = urlsplit(self.path).path
        if path.startswith("/api/acquisition"):
            from .acquisition import Acquisition
            acquisition = Acquisition(database, actor)
            if payload is not None:
                return acquisition.action(path, payload)
            if path == "/api/acquisition":
                return acquisition.snapshot()
            if path == "/api/acquisition/jobs":
                return acquisition.jobs(parse_qs(urlsplit(self.path).query).get("after_id",[None])[0])
            if path.startswith("/api/acquisition/jobs/"):
                return acquisition.job(path.rsplit("/", 1)[-1])
            raise ValueError("Unknown acquisition route")
        if payload is not None:
            return api.action(path, payload)
        if path == "/api/workspace":
            return api.snapshot()
        if path == "/api/overview":
            return api.overview()
        if path == "/api/library":
            return api.library()
        if path == "/api/leads":
            params = parse_qs(urlsplit(self.path).query)
            return api.leads(params.get("search", [""])[0], params.get("history", ["all"])[0], params.get("after_id", [None])[0])
        if path.startswith("/api/leads/"):
            return api.lead(path.rsplit("/", 1)[-1])
        if path == "/api/conversations":
            params = parse_qs(urlsplit(self.path).query)
            return api.conversations(params.get("before_time", [None])[0], params.get("before_id", [None])[0])
        if path.startswith("/api/conversations/"):
            return api.conversation(path.rsplit("/", 1)[-1])
        raise ValueError("Unknown owner route")

    def _static(self):
        root = Path(os.environ.get("CLIENT_FINDER_WEB_ROOT", "apps/control-center/dist")).resolve()
        route = unquote(urlsplit(self.path).path).lstrip("/") or "index.html"
        target = (root / route).resolve()
        if not target.is_relative_to(root) or not target.is_file() or target.suffix not in (".html", ".js", ".css", ".woff2", ".woff", ".svg", ".ico"):
            self._reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        import mimetypes
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self' https://mtdavgadkiiofwikzdtn.supabase.co; img-src 'self' data:; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/api/config":
            key = os.environ.get("SUPABASE_PUBLISHABLE_KEY", "")
            # Only a publishable key is exposed. Service-role JWTs are never accepted here.
            if not valid_api_key(key, public=True):
                key = ""
            configured = bool(key and os.environ.get("CLIENT_FINDER_OWNER_AUTH_ID") and
                              all(os.environ.get(name) for name in REQUIRED_CONFIGURATION[:3]))
            if configured:
                try:
                    uuid.UUID(os.environ["CLIENT_FINDER_OWNER_AUTH_ID"])
                    build_database()
                except (ValueError, ProviderError):
                    configured = False
            self._reply(HTTPStatus.OK, {"owner_email": OWNER_EMAIL,
                "supabase_url": "https://mtdavgadkiiofwikzdtn.supabase.co", "publishable_key": key,
                "configured": configured})
            return
        if self.path.startswith("/api/"):
            try:
                self._reply(HTTPStatus.OK, self._owner_api())
            except OwnerError:
                self._reply(HTTPStatus.FORBIDDEN, {"error": "personal_owner_sign_in_required"})
            except (KeyError, ProviderError):
                self._reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "personal_backend_unavailable"})
            except ValueError:
                self._reply(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            return
        if self.path != "/health":
            self._static()
            return
        configured = all(os.environ.get(key) for key in REQUIRED_CONFIGURATION[:3])
        if configured:
            try:
                # This is a local configuration check, not a claim that the
                # database, bot, Gmail, or n8n connections are healthy.
                build_database()
            except (ProviderError, ValueError):
                configured = False
        self._reply(HTTPStatus.OK if configured else HTTPStatus.SERVICE_UNAVAILABLE, {
            "status": "configured" if configured else "setup_incomplete"
        })

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            try:
                size = int(self.headers.get("Content-Length", "0"))
                maximum = 2_000_000 if urlsplit(self.path).path == "/api/acquisition/import-preview" else 100000
                if not 0 < size <= maximum:
                    raise ValueError("Invalid request size")
                result = self._owner_api(json.loads(self.rfile.read(size)))
                self._reply(HTTPStatus.OK, {"result": result})
            except OwnerError:
                self._reply(HTTPStatus.FORBIDDEN, {"error": "personal_owner_sign_in_required"})
            except (ValueError, KeyError):
                self._reply(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
            except ProviderError:
                self._reply(HTTPStatus.CONFLICT, {"error": "action_unconfirmed", "detail": "The action could not be confirmed. Refresh before retrying, and check the conversation, proof, sender footer, and sending limits."})
            return
        if self.path not in ("/discover", "/card", "/mail-poll", "/followups/due", "/inbox/sync", "/agents/run", "/replies/send", "/replies/reconcile", "/replies/cards", "/replies/telegram", "/acquisition/run", "/outreach/send", "/applications/send", "/applications/reconcile", "/applications/cards", "/jobs/intake"):
            self._reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        token = os.environ.get("CLIENT_FINDER_SERVICE_TOKEN", "")
        received = self.headers.get("Authorization", "")
        if not token or not hmac.compare_digest(received, "Bearer " + token):
            self._reply(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        required = REQUIRED_CONFIGURATION if self.path == "/discover" else REQUIRED_CONFIGURATION[:3]
        if not all(os.environ.get(key) for key in required):
            self._reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "provider_or_configuration_unavailable"})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            max_size = 4_000_000 if self.path == "/mail-poll" else 100000 if self.path in ("/replies/telegram", "/jobs/intake") else 2048
            if not 0 <= size <= max_size:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(size) or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("Invalid request body")
            if self.path == "/jobs/intake":
                from .acquisition import intake_jobs
                self._reply(HTTPStatus.OK,intake_jobs(build_database(),payload))
                return
            if self.path == "/acquisition/run":
                from .integrations import run_operation
                self._reply(HTTPStatus.OK, run_operation(build_database()))
                return
            if self.path in ("/applications/send", "/applications/reconcile", "/applications/cards"):
                from .applications import send_application, reconcile_application, ApplicationTelegram
                db=build_database()
                if self.path == "/applications/cards":
                    result=ApplicationTelegram(db).publish_one()
                elif self.path == "/applications/reconcile":
                    result=reconcile_application(db,str(uuid.UUID(payload["attempt_id"])))
                else:
                    result=send_application(db)
                self._reply(HTTPStatus.OK,result)
                return
            if self.path == "/inbox/sync":
                database = build_database()
                try:
                    gmail = Gmail.from_environment()
                except ProviderError:
                    database.rpc("client_finder_inbox_error", {})
                    raise
                self._reply(HTTPStatus.OK, InboxSync(gmail, database).run())
                return
            if self.path == "/agents/run":
                self._reply(HTTPStatus.OK, TaskRunner(build_database()).run_one())
                return
            if self.path == "/replies/send":
                self._reply(HTTPStatus.OK, send_one_reply(build_database()))
                return
            if self.path == "/outreach/send":
                self._reply(HTTPStatus.OK, send_one_reply(build_database(),_outreach=True))
                return
            if self.path == "/replies/reconcile":
                self._reply(HTTPStatus.OK, reconcile_reply(build_database(), str(uuid.UUID(payload["attempt_id"]))))
                return
            if self.path in ("/replies/cards", "/replies/telegram"):
                from .telegram_replies import ReplyTelegram
                bot = ReplyTelegram(build_database())
                if self.path == "/replies/telegram" and str(payload.get("callback_query",{}).get("data","")).startswith("a"):
                    from .applications import ApplicationTelegram
                    result=ApplicationTelegram(build_database()).callback(payload)
                else:
                    result = bot.publish_one() if self.path == "/replies/cards" else bot.callback(payload)
                self._reply(HTTPStatus.OK, result)
                return
            if self.path == "/mail-poll":
                if set(payload) != {"gmail_messages", "scanned_since", "scanned_until"}:
                    raise ValueError("Invalid mailbox poll request")
                messages = payload["gmail_messages"]
                if not isinstance(messages, list):
                    raise ValueError("Gmail messages must be a list")
                if not MAIL_POLL_LOCK.acquire(blocking=False):
                    self._reply(HTTPStatus.CONFLICT, {"error": "mail_poll_already_running"})
                    return
                try:
                    result = MailMonitor(build_database()).poll(
                        messages, str(payload["scanned_since"]), str(payload["scanned_until"])
                    )
                finally:
                    MAIL_POLL_LOCK.release()
                self._reply(HTTPStatus.OK, result)
                return
            if self.path == "/followups/due":
                if set(payload) - {"limit"}:
                    raise ValueError("Invalid follow-up request")
                limit = payload.get("limit", 5)
                if not isinstance(limit, int) or isinstance(limit, bool):
                    raise ValueError("Invalid follow-up limit")
                self._reply(HTTPStatus.OK, prepare_due_followups(build_database(), limit=limit))
                return
            if self.path == "/card":
                if set(payload) != {"message_id"}:
                    raise ValueError("Invalid card request")
                uuid.UUID(str(payload["message_id"]))
                self._reply(HTTPStatus.OK, stored_card(build_database(), str(payload["message_id"])))
                return
            if set(payload) - {"limit"}:
                raise ValueError("Invalid discovery request")
            limit = payload.get("limit", 5)
            if not isinstance(limit, int) or isinstance(limit, bool):
                raise ValueError("Invalid limit")
            if not DISCOVERY_LOCK.acquire(blocking=False):
                self._reply(HTTPStatus.CONFLICT, {"error": "discovery_already_running"})
                return
            try:
                result = build_runner().run(limit=limit)
            finally:
                DISCOVERY_LOCK.release()
            self._reply(HTTPStatus.OK, result.json())
        except (ValueError, json.JSONDecodeError):
            self._reply(HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
        except (KeyError, ProviderError):
            self._reply(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "provider_or_configuration_unavailable"})


def main() -> None:
    host = os.environ.get("CLIENT_FINDER_BIND", "127.0.0.1")
    port = int(os.environ.get("CLIENT_FINDER_PORT", "8088"))
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
