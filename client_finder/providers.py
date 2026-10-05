"""Small API clients. Paid calls require a successful database reservation."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


class ProviderError(Exception):
    pass


class ProviderConfigurationError(ProviderError):
    """A credentialed provider is pointed at an unexpected destination."""


EXPECTED_SUPABASE_URL = "https://mtdavgadkiiofwikzdtn.supabase.co"


def supabase_headers(key: str) -> dict[str, str]:
    headers = {"apikey": key}
    # Opaque publishable/secret keys are not JWT bearer tokens.
    if not key.startswith(("sb_secret_", "sb_publishable_")):
        headers["Authorization"] = f"Bearer {key}"
    return headers


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Never forward API credentials to a redirect destination."""

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int,
                         msg: str, headers: Any, newurl: str) -> None:
        return None


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    description: str


def _json_request(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> Any:
    encoded = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url, data=encoded, method=method,
        headers={"Accept": "application/json", **(headers or {}), **({"Content-Type": "application/json"} if payload is not None else {})},
    )
    try:
        with urllib.request.build_opener(_NoRedirects()).open(request, timeout=25) as response:
            body = response.read(2_000_001)
            if len(body) > 2_000_000:
                raise ProviderError("Provider response exceeded the limit")
            # PostgREST returns 204 for void RPCs, including task completion.
            # Do not turn a committed write into a JSON decoding failure.
            if getattr(response, "status", None) == 204 and not body:
                return None
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        raise ProviderError(f"Provider returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ProviderError("Provider request failed") from exc


class SupabaseRest:
    def __init__(self, url: str, service_key: str) -> None:
        if (not isinstance(url, str)
                or url not in (EXPECTED_SUPABASE_URL, EXPECTED_SUPABASE_URL + "/")
                or not isinstance(service_key, str) or not service_key.strip()):
            raise ProviderConfigurationError("The owned Hawkins Supabase URL and a service key are required")
        self.url = EXPECTED_SUPABASE_URL
        self.headers = {
            **supabase_headers(service_key),
            "Prefer": "return=representation",
        }

    def rpc(self, name: str, values: dict[str, Any]) -> Any:
        return _json_request(f"{self.url}/rest/v1/rpc/{name}", method="POST", payload=values, headers=self.headers)

    def rows(self, table: str, filters: dict[str, str], *, select: str = "*") -> list[dict[str, Any]]:
        query = urllib.parse.urlencode({"select": select, **filters})
        result = _json_request(f"{self.url}/rest/v1/{table}?{query}", headers=self.headers)
        if not isinstance(result, list):
            raise ProviderError("Unexpected Supabase response")
        return result

    def count(self, table: str, filters: dict[str, str] | None = None) -> int:
        """Read an exact total without transferring business records."""
        query = urllib.parse.urlencode({**(filters or {}), "select": "*", "limit": "0"})
        request = urllib.request.Request(f"{self.url}/rest/v1/{table}?{query}", method="HEAD",
            headers={**self.headers, "Prefer": "count=exact"})
        try:
            with urllib.request.build_opener(_NoRedirects()).open(request, timeout=25) as response:
                total = response.headers.get("Content-Range", "").rsplit("/", 1)[-1]
                if not total.isdigit():
                    raise ProviderError("Database count was not confirmed")
                return int(total)
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"Provider returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ProviderError("Provider count request failed") from exc

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        result = _json_request(f"{self.url}/rest/v1/{table}", method="POST", payload=values, headers=self.headers)
        if not isinstance(result, list) or len(result) != 1:
            raise ProviderError("Supabase insert did not return exactly one row")
        return result[0]

    def reserve_cost(self, provider: str, operation: str, max_cost_cents: float) -> str:
        result = self.rpc("client_finder_reserve_cost", {
            "idempotency_key": str(uuid.uuid4()), "provider": provider,
            "operation": operation, "max_cost_cents": max_cost_cents,
        })
        if not isinstance(result, dict) or not result.get("id"):
            raise ProviderError("Cost reservation was not confirmed")
        return str(result["id"])

    def settle_cost(self, reservation_id: str, actual_cents: float) -> None:
        self.rpc("client_finder_settle_cost", {"reservation_id": reservation_id, "actual_cents": actual_cents})

    def begin_cost_call(self, reservation_id: str) -> None:
        self.rpc("client_finder_begin_cost_call", {"reservation_id": reservation_id})


class BraveSearch:
    API = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, key: str, database: SupabaseRest) -> None:
        if not key:
            raise ValueError("A Brave Search API key is required")
        self.key = key
        self.database = database

    def search(self, query: str) -> list[SearchResult]:
        if not query or len(query) > 600:
            raise ValueError("Search query must contain 1 to 600 characters")
        reservation_id = self.database.reserve_cost("brave", "web_search", 0.5)
        self.database.begin_cost_call(reservation_id)
        params = urllib.parse.urlencode({"q": query, "country": "US", "search_lang": "en", "count": 20, "safesearch": "strict"})
        # A timeout may still be billed. Keep its reserved cent until manually
        # reconciled; no hidden retry is performed.
        payload = _json_request(self.API + "?" + params, headers={"X-Subscription-Token": self.key})
        self.database.settle_cost(reservation_id, 0.5)
        if not isinstance(payload, dict) or not isinstance(payload.get("web"), dict):
            raise ProviderError("Brave response has an unexpected shape")
        results = payload["web"].get("results", [])
        if not isinstance(results, list):
            raise ProviderError("Brave response had no web results list")
        return [
            SearchResult(str(row.get("title", ""))[:200], str(row.get("url", "")), str(row.get("description", ""))[:500])
            for row in results if isinstance(row, dict) and row.get("url")
        ]
