"""Turn raw resume text into a structured ResumeProfile via the chosen LLM."""

from __future__ import annotations

from .config import Settings
from .llm import parse_structured
from .models import ResumeProfile

_SYSTEM = (
    "You are an expert technical recruiter. Extract a structured profile from the "
    "candidate's resume. Infer target roles and seniority from their actual experience. "
    "Produce concise, high-signal search keywords a job portal would match on. "
    "Only use information present in the resume — never invent employers, skills, or names."
)


def analyze_resume(resume_text: str, settings: Settings) -> ResumeProfile:
    """Extract a ResumeProfile from resume text using structured outputs."""
    user = (
        "Analyze this resume and extract the structured profile.\n\n"
        "=== RESUME START ===\n"
        f"{resume_text}\n"
        "=== RESUME END ==="
    )
    return parse_structured(settings, _SYSTEM, user, ResumeProfile, max_tokens=4096)
