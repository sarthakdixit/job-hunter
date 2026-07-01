"""Fetch a company's careers page and extract individual job-posting links.

Recovers postings for sites where web search only indexed the landing page:
  1. Detects embedded ATS boards (Greenhouse, Lever) and queries their public
     JSON APIs — the most reliable source of clean per-posting URLs.
  2. Falls back to parsing <a> links out of the careers page HTML and keeping
     those that look like specific postings on the same site.

All network calls fail soft: any error yields an empty list so one bad site
never breaks the run.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from .models import Company
from .search import SearchHit, is_specific_posting

_UA = "Mozilla/5.0 (compatible; resume-job-finder/0.1)"

# ATS embed signatures found in careers-page HTML, capturing the board token.
# Greenhouse embeds carry the token in a `for=` param; standalone boards put it
# in the path (boards.greenhouse.io/<token>, job-boards.greenhouse.io/<token>).
_GREENHOUSE_FOR_RE = re.compile(r"greenhouse\.io/[^\"'\s]*?[?&]for=([A-Za-z0-9_-]+)", re.I)
_GREENHOUSE_PATH_RE = re.compile(
    r"(?:boards|job-boards)\.greenhouse\.io/([A-Za-z0-9_-]+)", re.I
)
_LEVER_RE = re.compile(r"jobs\.lever\.co/([A-Za-z0-9_-]+)", re.I)
_GH_NON_TOKENS = {"embed", "job_board", "js"}


class _AnchorParser(HTMLParser):
    """Collect (href, link_text) pairs from HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href")
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._text).strip()))
            self._href = None
            self._text = []


def extract_postings(
    company: Company,
    location: str | None = None,
    max_results: int = 5,
    timeout: float = 15.0,
) -> list[SearchHit]:
    """Return specific postings discovered from the company's careers page."""
    if not company.careers_url:
        return []

    try:
        resp = requests.get(
            company.careers_url, headers={"User-Agent": _UA}, timeout=timeout, allow_redirects=True
        )
        resp.raise_for_status()
        html = resp.text
    except Exception:  # noqa: BLE001 - fail soft, skip this company
        return []

    return extract_from_html(company, html, company.careers_url, location, max_results, timeout)


def extract_from_html(
    company: Company,
    html: str,
    base_url: str,
    location: str | None = None,
    max_results: int = 5,
    timeout: float = 15.0,
) -> list[SearchHit]:
    """Extract postings from already-fetched HTML (static or browser-rendered).

    Shared by the static fetch path and the Playwright renderer.
    """
    hits: list[SearchHit] = []
    seen: set[str] = set()

    def add(title: str, link: str, snippet: str = "") -> None:
        if link and link.startswith("http") and link not in seen:
            seen.add(link)
            hits.append(SearchHit(company=company.name, title=title or link, url=link, snippet=snippet))

    # 1. Embedded ATS boards (most reliable).
    for title, link, loc in _ats_postings(html, location, timeout):
        add(title, link, loc)
        if len(hits) >= max_results:
            return hits[:max_results]

    # 2. Anchor links on the page that look like individual postings.
    parser = _AnchorParser()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML, use whatever parsed
        pass
    for href, text in parser.links:
        full = urljoin(base_url, href)
        if company.domain and not _same_site(full, company.domain):
            continue
        if not is_specific_posting(full, text):
            continue
        add(text, full)
        if len(hits) >= max_results:
            break

    return hits[:max_results]


def _ats_postings(
    html: str, location: str | None, timeout: float
) -> list[tuple[str, str, str]]:
    """Return (title, url, location) tuples from any embedded ATS board."""
    out: list[tuple[str, str, str]] = []

    token = _greenhouse_token(html)
    if token:
        out.extend(_greenhouse(token, location, timeout))

    lv = _LEVER_RE.search(html)
    if lv and lv.group(1).lower() not in _GH_NON_TOKENS:
        out.extend(_lever(lv.group(1), location, timeout))

    return out


def _greenhouse_token(html: str) -> str | None:
    """Extract a Greenhouse board token from careers-page HTML, if embedded."""
    m = _GREENHOUSE_FOR_RE.search(html)
    if m and m.group(1).lower() not in _GH_NON_TOKENS:
        return m.group(1)
    for m in _GREENHOUSE_PATH_RE.finditer(html):
        if m.group(1).lower() not in _GH_NON_TOKENS:
            return m.group(1)
    return None


def _greenhouse(token: str, location: str | None, timeout: float) -> list[tuple[str, str, str]]:
    api = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    data = _get_json(api, timeout)
    out: list[tuple[str, str, str]] = []
    for job in (data or {}).get("jobs", []):
        loc = (job.get("location") or {}).get("name", "") or ""
        if not _location_ok(loc, location):
            continue
        out.append((job.get("title", ""), job.get("absolute_url", ""), loc))
    return out


def _lever(token: str, location: str | None, timeout: float) -> list[tuple[str, str, str]]:
    api = f"https://api.lever.co/v0/postings/{token}?mode=json"
    data = _get_json(api, timeout)
    out: list[tuple[str, str, str]] = []
    for job in data or []:
        loc = (job.get("categories") or {}).get("location", "") or ""
        if not _location_ok(loc, location):
            continue
        out.append((job.get("text", ""), job.get("hostedUrl", ""), loc))
    return out


def _get_json(url: str, timeout: float):
    try:
        resp = requests.get(url, headers={"User-Agent": _UA}, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception:  # noqa: BLE001 - fail soft
        return None


def _location_ok(job_location: str, wanted: str | None) -> bool:
    """True if the posting's location matches the wanted region (or is unknown)."""
    if not wanted or not job_location:
        return True
    jl = job_location.lower()
    # `wanted` looks like "Bengaluru, India" — match on any of its parts.
    return any(part.strip().lower() in jl for part in wanted.split(",") if part.strip())


def _same_site(url: str, domain: str) -> bool:
    return _registrable(urlparse(url).netloc.lower()) == _registrable(domain.lower())


def _registrable(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host
