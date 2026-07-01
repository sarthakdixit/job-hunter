"""Rank search hits against the resume with the chosen LLM, keeping good fits."""

from __future__ import annotations

import json

from pydantic import BaseModel

from .config import Settings
from .llm import parse_structured
from .models import JobMatch, ResumeProfile
from .search import SearchHit


class _MatchResult(BaseModel):
    matches: list[JobMatch]


_SYSTEM = (
    "You are an expert technical recruiter matching a candidate to specific job "
    "listings found on companies' own career portals.\n"
    "Rules:\n"
    "- Score each listing 0-100 for how well it fits THIS candidate's profile.\n"
    "- Only return listings that are plausibly real openings the candidate could apply to.\n"
    "- For contact fields (apply_url, careers_email, company_linkedin), ONLY include a value "
    "if it appears explicitly in the provided title/snippet/url. Never guess or fabricate "
    "personal names or private emails — official/public channels only. Use null when absent.\n"
    "- Prefer the direct application URL when present; otherwise use the listing url."
)


def match_jobs(
    profile: ResumeProfile,
    hits: list[SearchHit],
    settings: Settings,
    min_score: int = 60,
    top_n: int = 25,
) -> tuple[list[JobMatch], int]:
    """Score search hits against the profile.

    Returns (matches, listings_sent) — the second value is how many de-duplicated
    listings were actually sent to the LLM (bounded by settings.max_listings).
    """
    if not hits:
        return [], 0

    # De-duplicate by URL — search often returns the same posting several times.
    seen: set[str] = set()
    listings: list[dict] = []
    for h in hits:
        if h.url in seen:
            continue
        seen.add(h.url)
        listings.append(
            {"company": h.company, "title": h.title, "url": h.url, "snippet": h.snippet[:500]}
        )

    # Bound the payload so the matching call stays fast and within token limits.
    listings = listings[: settings.max_listings]

    user = (
        "Candidate profile:\n"
        f"{profile.model_dump_json(indent=2)}\n\n"
        "Job listings found on company career portals:\n"
        f"{json.dumps(listings, indent=2)}\n\n"
        "Return the matches, best fit first."
    )
    result = parse_structured(
        settings, _SYSTEM, user, _MatchResult, max_tokens=8192, effort=settings.match_effort
    )

    matches = [m for m in result.matches if m.fit_score >= min_score]
    matches.sort(key=lambda m: m.fit_score, reverse=True)
    return matches[:top_n], len(listings)
