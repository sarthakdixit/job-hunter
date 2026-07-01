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
) -> list[JobMatch]:
    """Score search hits against the profile and return the best matches."""
    if not hits:
        return []

    listings = [
        {"company": h.company, "title": h.title, "url": h.url, "snippet": h.snippet[:600]}
        for h in hits
    ]

    user = (
        "Candidate profile:\n"
        f"{profile.model_dump_json(indent=2)}\n\n"
        "Job listings found on company career portals:\n"
        f"{json.dumps(listings, indent=2)}\n\n"
        "Return the matches, best fit first."
    )
    result = parse_structured(settings, _SYSTEM, user, _MatchResult, max_tokens=8192)

    matches = [m for m in result.matches if m.fit_score >= min_score]
    matches.sort(key=lambda m: m.fit_score, reverse=True)
    return matches[:top_n]
