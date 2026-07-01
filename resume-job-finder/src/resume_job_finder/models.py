"""Shared data models.

Pydantic is used throughout so the LLM-extracted structures can be validated
directly via `client.messages.parse(...)`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResumeProfile(BaseModel):
    """Structured summary of a candidate, extracted from their resume."""

    full_name: str | None = Field(None, description="Candidate name, if present")
    target_roles: list[str] = Field(
        default_factory=list,
        description="Job titles this candidate is a fit for, most likely first",
    )
    seniority: str = Field(
        "unknown",
        description="One of: intern, junior, mid, senior, lead, principal, executive, unknown",
    )
    skills: list[str] = Field(default_factory=list, description="Key hard skills / tools")
    domains: list[str] = Field(
        default_factory=list,
        description="Industries / domains the candidate has experience in",
    )
    years_experience: float | None = Field(None, description="Approx. total years of experience")
    search_keywords: list[str] = Field(
        default_factory=list,
        description="Concise keywords to use when searching job portals",
    )
    summary: str = Field("", description="One-paragraph candidate summary")


class Company(BaseModel):
    """A company we are allowed to search (a curated or user-supplied entry)."""

    name: str
    careers_url: str = Field(..., description="URL of the company's own careers/jobs page")
    domain: str = Field(..., description="Careers portal domain, e.g. careers.google.com")


class JobMatch(BaseModel):
    """A ranked opening found on a company's career portal."""

    company: str
    title: str
    url: str
    location: str | None = None
    fit_score: int = Field(..., ge=0, le=100, description="0-100 fit vs the resume")
    reasoning: str = Field("", description="Why this role fits the candidate")
    # Public / official channels only — never scraped personal data.
    apply_url: str | None = None
    careers_email: str | None = Field(
        None, description="Publicly listed recruiting email, if present in the source"
    )
    company_linkedin: str | None = Field(
        None, description="Company LinkedIn page, if present in the source"
    )
