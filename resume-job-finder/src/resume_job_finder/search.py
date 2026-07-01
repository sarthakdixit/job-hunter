"""Scoped web search over company career portals via Tavily.

Every query is constrained to a company's own careers domain (when known) and
explicitly excludes job aggregators (LinkedIn, Naukri, Indeed, ATS hosts, ...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from tavily import TavilyClient

from .config import BLOCKED_DOMAINS, Settings
from .models import Company, ResumeProfile


@dataclass
class SearchHit:
    company: str
    title: str
    url: str
    snippet: str


# A numeric requisition id (4+ digits) is a strong "specific posting" signal.
_ID_RE = re.compile(r"\d{4,}")
# Path/query fragments that indicate an individual posting rather than a listing.
_POSTING_RE = re.compile(
    r"(/job/|/jobs/[^/]+|/job-|/position|/opening|/vacanc|/requisition|/posting"
    r"|gh_jid=|job[_-]?id=|/careers?/[^/]+-\d|/detail/)",
    re.I,
)
# Last path segment values that mean "this is a landing/search page", not a posting.
_GENERIC_SEGMENTS = {
    "careers", "career", "jobs", "job", "search", "job-search", "openings",
    "opportunities", "apply", "vacancies", "life", "students", "home", "index.html",
    "careers.html", "en", "en-us", "us", "india", "global", "overview", "",
}


def is_specific_posting(url: str, title: str = "") -> bool:
    """Heuristic: does this URL point at an individual job posting?

    Filters out careers home/search/landing pages so results are actionable
    postings rather than a list of portals. Errs toward keeping deep, id- or
    slug-bearing URLs and dropping shallow generic ones.
    """
    p = urlparse(url)
    query = p.query or ""
    # Job id carried in a query string (e.g. ?gh_jid=123456 or ?jobId=987654).
    if _POSTING_RE.search("?" + query) or _ID_RE.search(query):
        return True

    segments = [s for s in p.path.split("/") if s]
    if len(segments) < 2:
        return False  # root or single-segment page like /careers or /jobs

    last = segments[-1].lower()
    # Search/results/listing pages are aggregations, never a single posting.
    if any(word in last for word in ("search", "result", "listing")):
        return False
    if _ID_RE.search(p.path):
        return True  # explicit requisition id somewhere in the path
    if _POSTING_RE.search(p.path) and last not in _GENERIC_SEGMENTS:
        return True  # posting keyword followed by a real slug
    # A descriptive slug (hyphenated, non-generic) is usually a posting title.
    if last not in _GENERIC_SEGMENTS and "-" in last and len(last) > 8:
        return True
    return False


def build_query(profile: ResumeProfile, company: Company, location: str | None = None) -> str:
    """Construct a focused careers-page query for one company.

    `location` (e.g. "Bengaluru, India" or "India") biases results toward roles
    in that region — essential for global MNCs whose sites list worldwide jobs.
    """
    role = profile.target_roles[0] if profile.target_roles else "job"
    keywords = " ".join(profile.search_keywords[:4])
    scope = "" if company.domain else f'"{company.name}" careers'
    loc = f"in {location}" if location else ""
    return " ".join(part for part in (role, keywords, scope, loc, "jobs openings") if part).strip()


def search_company(
    client: TavilyClient,
    profile: ResumeProfile,
    company: Company,
    max_results: int = 5,
    location: str | None = None,
    postings_only: bool = True,
) -> list[SearchHit]:
    """Search a single company's career portal for relevant openings.

    When `postings_only` is True (default), results are filtered to URLs that
    look like individual job postings, dropping careers landing/search pages.
    We over-fetch so there are enough candidates left after filtering.
    """
    query = build_query(profile, company, location)

    kwargs: dict = {
        "query": query,
        "search_depth": "advanced",
        # Over-fetch: filtering to real postings discards landing pages.
        "max_results": min(20, max(max_results * 3, 10)) if postings_only else max_results,
    }
    if company.domain:
        # Constrain strictly to the company's own careers domain.
        kwargs["include_domains"] = [company.domain]
    else:
        # No known domain: search broadly but keep aggregators out.
        kwargs["exclude_domains"] = BLOCKED_DOMAINS

    try:
        response = client.search(**kwargs)
    except Exception as exc:  # noqa: BLE001 - surface per-company failures, keep going
        raise SearchError(str(exc)) from exc

    postings: list[SearchHit] = []
    for r in response.get("results", []):
        url = r.get("url", "")
        if _is_blocked(url):
            continue
        hit = SearchHit(
            company=company.name,
            title=r.get("title", "").strip(),
            url=url,
            snippet=(r.get("content") or "").strip(),
        )
        if postings_only and not is_specific_posting(url, hit.title):
            continue
        postings.append(hit)
        if len(postings) >= max_results:
            break
    return postings


def make_client(settings: Settings) -> TavilyClient:
    return TavilyClient(api_key=settings.tavily_api_key)


class SearchError(RuntimeError):
    """Raised when a single company search fails."""


def _is_blocked(url: str) -> bool:
    return any(blocked in url.lower() for blocked in BLOCKED_DOMAINS)
