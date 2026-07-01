"""Configuration and API-key loading."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Job aggregators / boards we must never search — only company-owned portals.
# Note: ATS hosts (Greenhouse, Lever, Workday, SmartRecruiters, Ashby) are NOT
# blocked — they host many companies' real application flows, so listings there
# are legitimate "apply on the company's process" links, not aggregator noise.
BLOCKED_DOMAINS: list[str] = [
    "linkedin.com",
    "naukri.com",
    "indeed.com",
    "glassdoor.com",
    "monster.com",
    "ziprecruiter.com",
    "shine.com",
    "timesjobs.com",
    "dice.com",
    "simplyhired.com",
    "wellfound.com",
    "angel.co",
    "foundit.in",
    "instahyre.com",
    "cutshort.io",
    "hirist.com",
]


DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-8"
DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"
PROVIDERS = ("anthropic", "gemini")


@dataclass
class Settings:
    provider: str
    tavily_api_key: str
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    gemini_model: str = DEFAULT_GEMINI_MODEL
    effort: str = "high"
    match_effort: str = "medium"
    timeout: float = 180.0
    max_listings: int = 120

    @property
    def model(self) -> str:
        """The model name for the active provider."""
        return self.gemini_model if self.provider == "gemini" else self.anthropic_model

    @classmethod
    def load(cls, provider: str | None = None) -> "Settings":
        provider = (provider or os.getenv("RJF_PROVIDER", "anthropic")).strip().lower()
        if provider not in PROVIDERS:
            raise RuntimeError(
                f"Unknown provider '{provider}'. Choose one of: {', '.join(PROVIDERS)}."
            )

        tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

        # Tavily is always required; the LLM key depends on the chosen provider.
        required: list[tuple[str, str]] = [("TAVILY_API_KEY", tavily_key)]
        if provider == "anthropic":
            required.append(("ANTHROPIC_API_KEY", anthropic_key))
        else:
            required.append(("GEMINI_API_KEY", gemini_key))

        missing = [name for name, val in required if not val]
        if missing:
            raise RuntimeError(
                f"Missing required environment variable(s) for provider '{provider}': "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill them in."
            )

        return cls(
            provider=provider,
            tavily_api_key=tavily_key,
            anthropic_api_key=anthropic_key,
            gemini_api_key=gemini_key,
            anthropic_model=os.getenv("RJF_MODEL", DEFAULT_ANTHROPIC_MODEL).strip(),
            gemini_model=os.getenv("RJF_GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip(),
            effort=os.getenv("RJF_EFFORT", "high").strip(),
            match_effort=os.getenv("RJF_MATCH_EFFORT", "medium").strip(),
            timeout=float(os.getenv("RJF_TIMEOUT", "180")),
            max_listings=int(os.getenv("RJF_MAX_LISTINGS", "120")),
        )
