"""Bounded public-site research. External text is data, never instructions."""

from __future__ import annotations

import html
import http.client
import ipaddress
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser


USER_AGENT = "HawkinsClientFinder/1.0 (+https://armageddonvivas.cloud/)"
MAX_HTML_BYTES = 512_000
MAX_REDIRECTS = 3
MAX_PAGES_PER_SITE = 3
CONTACT_WORDS = ("contact", "get-in-touch", "about", "team", "careers")
AGENCY_WORDS = ("agency", "studio", "marketing", "digital services", "web development")
SIGNAL_WORDS = (
    "client portal", "customer portal", "web app", "internal tool", "application development",
    "proposal", "sales document", "scope of work", "statement of work",
    "lead generation", "lead intake", "appointment booking", "booking reminders",
    "go high level", "gohighlevel", "crm automation", "rfp", "request for proposal",
    "knowledge base", "document assistant", "document workflow",
)
US_LOCATION = re.compile(
    r"\b(?:United States|USA|U\.S\.A\.|"
    r"Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|"
    r"Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|Kansas|Kentucky|"
    r"Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|"
    r"Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|New Mexico|"
    r"New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|"
    r"Rhode Island|South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|"
    r"Virginia|Washington|West Virginia|Wisconsin|Wyoming)\b",
    re.IGNORECASE,
)
CITY_STATE = re.compile(r"\b[A-Z][a-z]+(?: [A-Z][a-z]+)?,\s*(?:CA|NY|TX|FL|IL|WA|MA|CO|GA|NC|PA|AZ|VA|OH|MI|NJ|OR|TN|MD|MN|MO|WI)\b")
EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
THIRD_PARTY_LOCATION = re.compile(r"\b(?:clients?|customers?|partners?|candidates?|employees?|staff|jobs?)\b", re.IGNORECASE)
COMPANY_LOCATION = re.compile(
    r"\b(?:we(?:'re| are)|our\s+(?:agency|studio|company|team|office|headquarters)|"
    r"(?:the|this)\s+(?:agency|studio|company|office|headquarters)|"
    r"(?:agency|studio|company|office|headquarters))\s+(?:is\s+|are\s+)?"
    r"(?:based|located|headquartered)\s+in\s*$",
    re.IGNORECASE,
)
ADDRESS_LABEL = re.compile(r"(?:^|[.;])\s*(?:(?:our|the)\s+)?(?:office|headquarters|address)\s*:\s*$", re.IGNORECASE)


class ResearchError(Exception):
    """A retryable or reviewable research failure."""


class UnsafeDestination(ResearchError):
    """The requested destination failed the public-Internet check."""


@dataclass(frozen=True)
class Page:
    url: str
    text: str
    title: str
    description: str
    links: tuple[str, ...]
    published_emails: tuple[str, ...]


@dataclass(frozen=True)
class Observation:
    text: str
    source_url: str
    observed_at: str
    signal_type: str = "service"


@dataclass
class SiteResearch:
    company_name: str
    company_url: str
    domain: str
    location: str
    location_source_url: str
    contact_email: str
    contact_source_url: str
    contact_name: str = ""
    contact_role: str = ""
    observations: list[Observation] = field(default_factory=list)
    pages_checked: list[str] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)


def public_url(value: str) -> str:
    """Reject credentials, IP literals, odd ports, and non-web schemes."""
    parsed = urlsplit(value.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise UnsafeDestination("Only absolute public HTTP(S) URLs are allowed")
    if parsed.username or parsed.password or parsed.fragment:
        raise UnsafeDestination("URL credentials and fragments are not allowed")
    try:
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise UnsafeDestination("Invalid public hostname") from exc
    if not re.fullmatch(r"[a-z0-9.-]+", host) or ".." in host:
        raise UnsafeDestination("Invalid public hostname")
    if not host or "." not in host or host.endswith((".local", ".internal", ".localhost")):
        raise UnsafeDestination("A public DNS hostname is required")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise UnsafeDestination("IP-literal destinations are not allowed")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeDestination("Invalid port") from exc
    if port not in (None, 80, 443):
        raise UnsafeDestination("Nonstandard ports are not allowed")
    if parsed.scheme.lower() == "https" and port == 80:
        raise UnsafeDestination("Mismatched URL scheme and port")
    if parsed.scheme.lower() == "http" and port == 443:
        raise UnsafeDestination("Mismatched URL scheme and port")
    netloc = host if not port or port in (80, 443) else f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _public_addresses(host: str, port: int) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ResearchError("DNS lookup failed") from exc
    addresses = sorted({item[4][0] for item in answers})
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise UnsafeDestination("DNS did not resolve exclusively to public addresses")
    return addresses


def _get_once(url: str, *, max_bytes: int = MAX_HTML_BYTES) -> tuple[int, dict[str, str], bytes]:
    """Resolve and pin a public IP before opening a connection to prevent DNS rebinding."""
    checked = public_url(url)
    parts = urlsplit(checked)
    host = parts.hostname or ""
    port = 443 if parts.scheme == "https" else 80
    address = _public_addresses(host, port)[0]
    path = urlunsplit(("", "", parts.path or "/", parts.query, ""))
    connection = http.client.HTTPSConnection(host, port, timeout=8, context=ssl.create_default_context()) if parts.scheme == "https" else http.client.HTTPConnection(host, port, timeout=8)
    # HTTPConnection uses this address for TCP while TLS still checks the hostname.
    def connect_to_pinned_address() -> None:
        raw = socket.create_connection((address, port), timeout=8)
        connection.sock = connection._context.wrap_socket(raw, server_hostname=host) if parts.scheme == "https" else raw

    connection.connect = connect_to_pinned_address
    try:
        connection.request("GET", path, headers={"Host": host, "User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.9", "Connection": "close"})
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        if response.status in (301, 302, 303, 307, 308):
            return response.status, headers, b""
        if response.status == 404:
            return response.status, headers, b""
        if response.status != 200:
            raise ResearchError(f"Page returned HTTP {response.status}")
        length = headers.get("content-length")
        if length:
            try:
                if int(length) > max_bytes:
                    raise ResearchError("Page exceeds the size limit")
            except ValueError as exc:
                raise ResearchError("Invalid page size header") from exc
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ResearchError("Page exceeds the size limit")
        return response.status, headers, body
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        raise ResearchError("Could not fetch the public page") from exc
    finally:
        connection.close()


def _same_site_host(first: str, second: str) -> bool:
    return first.removeprefix("www.") == second.removeprefix("www.")


def _get_redirected(url: str, *, max_bytes: int = MAX_HTML_BYTES,
                    allow_missing_robots: bool = False,
                    can_fetch: Callable[[str], bool] | None = None) -> tuple[str, dict[str, str], bytes]:
    current = public_url(url)
    original_host = urlsplit(current).hostname or ""
    for _ in range(MAX_REDIRECTS + 1):
        if can_fetch is not None and not can_fetch(current):
            raise ResearchError("Site disallows automated access")
        status, headers, body = _get_once(current, max_bytes=max_bytes)
        if status == 200:
            return current, headers, body
        if status == 404:
            if allow_missing_robots:
                return current, headers, b""
            raise ResearchError("Page returned HTTP 404")
        target = headers.get("location")
        if not target:
            raise ResearchError("Redirect has no destination")
        next_url = public_url(urljoin(current, target))
        if urlsplit(current).scheme == "https" and urlsplit(next_url).scheme != "https":
            raise UnsafeDestination("HTTPS downgrade is not allowed")
        if not _same_site_host(original_host, urlsplit(next_url).hostname or ""):
            raise ResearchError("Redirect leaves the company site")
        current = next_url
    raise ResearchError("Too many redirects")


class _ContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ignored = 0
        self.title_mode = False
        self.title: list[str] = []
        self.description = ""
        self.text: list[str] = []
        self.links: list[str] = []
        self.emails: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.ignored += 1
        if tag == "title":
            self.title_mode = True
        if tag == "meta" and str(attributes.get("name") or "").lower() == "description":
            self.description = attributes.get("content", "") or ""
        if tag == "a":
            href = attributes.get("href", "") or ""
            if href.lower().startswith("mailto:"):
                self.emails.extend(EMAIL.findall(href[7:].split("?", 1)[0]))
            elif href:
                self.links.append(href)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.ignored:
            self.ignored -= 1
        if tag == "title":
            self.title_mode = False
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "footer"}:
            self.text.append("\n")

    def handle_data(self, data: str) -> None:
        if self.title_mode:
            self.title.append(data)
        elif not self.ignored:
            self.text.append(data)


def parse_page(url: str, raw_html: str) -> Page:
    parser = _ContentParser()
    parser.feed(raw_html)
    visible = html.unescape(" ".join(parser.text))
    visible = re.sub(r"[\t ]+", " ", visible)
    visible = re.sub(r"\n\s*\n+", "\n", visible).strip()
    emails = parser.emails + EMAIL.findall(visible)
    return Page(
        url=url,
        text=visible[:40_000],
        title=" ".join(parser.title).strip()[:200],
        description=parser.description[:500],
        links=tuple(parser.links[:300]),
        published_emails=tuple(dict.fromkeys(e.lower() for e in emails if len(e) <= 254)),
    )


class SafeSiteFetcher:
    def __init__(self) -> None:
        self._robots: dict[str, RobotFileParser] = {}
        self._last_fetch: dict[str, float] = {}

    def _allowed(self, url: str) -> bool:
        parsed = urlsplit(public_url(url))
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            robots = RobotFileParser()
            robots.set_url(origin + "/robots.txt")
            try:
                final, headers, data = _get_redirected(origin + "/robots.txt", max_bytes=64_000, allow_missing_robots=True)
                if not _same_site_host(urlsplit(final).hostname or "", parsed.hostname or ""):
                    raise ResearchError("Robots file redirected to a different host")
                if data and not headers.get("content-type", "").lower().startswith(("text/plain", "application/octet-stream")):
                    raise ResearchError("Robots file is not plain text")
                robots.parse(data.decode("utf-8", errors="replace").splitlines())
            except ResearchError:
                # Unknown access policy is a review task, not automatic permission.
                raise ResearchError("Could not verify robots access")
            self._robots[origin] = robots
        return self._robots[origin].can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> Page:
        checked = public_url(url)
        host = urlsplit(checked).hostname or ""
        pause = 1.0 - (time.monotonic() - self._last_fetch.get(host, 0.0))
        if pause > 0:
            time.sleep(pause)
        final, headers, body = _get_redirected(checked, can_fetch=self._allowed)
        self._last_fetch[host] = time.monotonic()
        if not _same_site_host(urlsplit(final).hostname or "", host):
            raise ResearchError("Page redirected to another domain")
        if not headers.get("content-type", "").lower().startswith(("text/html", "text/plain")):
            raise ResearchError("Page is not HTML or text")
        charset = "utf-8"
        match = re.search(r"charset=([\w-]+)", headers.get("content-type", ""), re.IGNORECASE)
        if match:
            charset = match.group(1)
        try:
            content = body.decode(charset, errors="replace")
        except LookupError:
            content = body.decode("utf-8", errors="replace")
        return parse_page(final, content)


def _contact_pages(homepage: Page) -> list[str]:
    domain = urlsplit(homepage.url).hostname
    found: list[str] = []
    links = sorted(homepage.links, key=lambda link: (
        0 if "contact" in link.lower() or "get-in-touch" in link.lower()
        else 1 if "career" in link.lower() or "hiring" in link.lower()
        else 2
    ))
    for link in links:
        if not any(word in link.lower() for word in CONTACT_WORDS):
            continue
        try:
            checked = public_url(urljoin(homepage.url, link))
        except UnsafeDestination:
            continue
        if urlsplit(checked).hostname == domain and checked != homepage.url and checked not in found:
            found.append(checked)
        if len(found) >= MAX_PAGES_PER_SITE - 1:
            break
    return found


def _business_email(pages: list[Page], domain: str) -> tuple[str, str]:
    for page in pages:
        for address in page.published_emails:
            name = address.rsplit("@", 1)[-1]
            if name == domain or name == domain.removeprefix("www."):
                if not address.lower().startswith(("noreply@", "no-reply@", "privacy@", "support@")):
                    return address, page.url
    return "", ""


def _agency_location(line: str) -> str:
    """Accept a US place only when the line refers to the agency itself."""
    for match in list(US_LOCATION.finditer(line)) + list(CITY_STATE.finditer(line)):
        context = line[:match.start()]
        clause = re.split(r"[.!?;]", context)[-1]
        if THIRD_PARTY_LOCATION.search(clause):
            continue
        if COMPANY_LOCATION.search(clause) or ADDRESS_LABEL.search(clause):
            return match.group(0)
    return ""


def research_site(url: str, *, fetcher: SafeSiteFetcher, observed_at: str,
                  focus_url: str | None = None) -> SiteResearch:
    homepage = fetcher.fetch(url)
    domain = urlsplit(homepage.url).hostname or ""
    pages = [homepage]
    result = SiteResearch(
        company_name=(homepage.title.split("|")[0].split(" — ")[0].strip() or domain)[:160],
        company_url=homepage.url,
        domain=domain.removeprefix("www."),
        location="",
        location_source_url="",
        contact_email="",
        contact_source_url="",
    )
    selected: list[str] = []
    if focus_url:
        focused = public_url(focus_url)
        if not _same_site_host(urlsplit(focused).hostname or "", domain):
            raise UnsafeDestination("Search result page is outside the company site")
        if (urlsplit(focused).path, urlsplit(focused).query) != (urlsplit(homepage.url).path, urlsplit(homepage.url).query):
            selected.append(focused)
    for link in _contact_pages(homepage):
        if len(selected) >= MAX_PAGES_PER_SITE - 1:
            break
        if link not in selected:
            selected.append(link)
    for link in selected:
        try:
            pages.append(fetcher.fetch(link))
        except ResearchError as exc:
            result.needs_review.append(f"{link}: {exc}")
    result.pages_checked = [page.url for page in pages]
    result.contact_email, result.contact_source_url = _business_email(pages, result.domain)
    homepage_summary = " ".join((homepage.title, homepage.description, homepage.text[:4000])).lower()
    if not any(word in homepage_summary for word in AGENCY_WORDS):
        result.needs_review.append("Agency identity is not established from the homepage")
    for page in pages:
        if not result.location:
            for line in page.text.splitlines():
                location = _agency_location(line)
                if location:
                    result.location = location
                    result.location_source_url = page.url
                    break
    for page in sorted(pages, key=lambda item: 0 if "career" in item.url or "hiring" in item.url else 1):
        for line in re.split(r"[\n.!?]", page.text):
            clean = " ".join(line.split())
            if 25 <= len(clean) <= 240 and any(word in clean.lower() for word in SIGNAL_WORDS):
                hiring = bool(re.search(r"\b(?:we(?:'re| are) hiring|join our team|open position|looking for a|seeking a)\b", clean, re.I))
                request = bool(re.search(r"\b(?:request for proposals|seeking proposals|submit a proposal)\b", clean, re.I))
                result.observations.append(Observation(
                    clean, page.url, observed_at,
                    "project_request" if request else "hiring" if hiring else "service",
                ))
                if len(result.observations) >= 12:
                    break
        if len(result.observations) >= 12:
            break
    if not result.location:
        result.needs_review.append("US location not established from company pages")
    if not result.contact_email:
        result.needs_review.append("Published company-domain email not found")
    if not result.observations:
        result.needs_review.append("No agency service or hiring evidence found")
    return result
