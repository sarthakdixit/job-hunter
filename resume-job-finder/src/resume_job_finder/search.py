"""Scoped web search over company career portals via Tavily.

Every query is constrained to a company's own careers domain (when known) and
explicitly excludes job aggregators (LinkedIn, Naukri, Indeed, ATS hosts, ...).
"""

from __future__ import annotations

from dataclasses import dataclass

from tavily import TavilyClient

from .config import BLOCKED_DOMAINS, Settings
from .models import Company, ResumeProfile


@dataclass
class SearchHit:
    company: str
    title: str
    url: str
    snippet: str


def build_query(profile: ResumeProfile, company: Company) -> str:
    """Construct a focused careers-page query for one company."""
    role = profile.target_roles[0] if profile.target_roles else "job"
    keywords = " ".join(profile.search_keywords[:4])
    scope = "" if company.domain else f'"{company.name}" careers'
    return f"{role} {keywords} {scope} jobs openings".strip()


def search_company(
    client: TavilyClient,
    profile: ResumeProfile,
    company: Company,
    max_results: int = 5,
) -> list[SearchHit]:
    """Search a single company's career portal for relevant openings."""
    query = build_query(profile, company)

    kwargs: dict = {
        "query": query,
        "search_depth": "advanced",
        "max_results": max_results,
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

    hits: list[SearchHit] = []
    for r in response.get("results", []):
        url = r.get("url", "")
        if _is_blocked(url):
            continue
        hits.append(
            SearchHit(
                company=company.name,
                title=r.get("title", "").strip(),
                url=url,
                snippet=(r.get("content") or "").strip(),
            )
        )
    return hits


def make_client(settings: Settings) -> TavilyClient:
    return TavilyClient(api_key=settings.tavily_api_key)


class SearchError(RuntimeError):
    """Raised when a single company search fails."""


def _is_blocked(url: str) -> bool:
    return any(blocked in url.lower() for blocked in BLOCKED_DOMAINS)
