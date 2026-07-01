"""Load the set of companies we are allowed to search.

Two sources, both producing `Company` objects:
  1. Curated per-country JSON bundled under data/companies/<code>.json
  2. A user-supplied list file (.json / .csv / .txt)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlparse

from .models import Company

# data/ lives at the repo root: <root>/data/companies, <root>/src/resume_job_finder
_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "companies"


def available_countries() -> list[str]:
    """Country codes we ship curated lists for (e.g. ['in', 'us'])."""
    if not _DATA_DIR.exists():
        return []
    return sorted(p.stem for p in _DATA_DIR.glob("*.json"))


def load_curated(country_code: str) -> list[Company]:
    """Load the curated top-companies list for a country code (case-insensitive)."""
    path = _DATA_DIR / f"{country_code.lower()}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No curated company list for country '{country_code}'. "
            f"Available: {', '.join(available_countries()) or '(none)'}. "
            "Provide your own with --companies."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [_coerce(entry) for entry in raw]


def load_user_list(path: str | Path) -> list[Company]:
    """Load a user-supplied company list. Accepts .json, .csv, or .txt."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Company list not found: {p}")

    suffix = p.suffix.lower()
    if suffix == ".json":
        raw = json.loads(p.read_text(encoding="utf-8"))
        return [_coerce(entry) for entry in raw]
    if suffix == ".csv":
        with p.open(newline="", encoding="utf-8") as fh:
            return [_coerce(row) for row in csv.DictReader(fh)]
    if suffix in (".txt", ".md"):
        companies = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                companies.append(_coerce({"name": line}))
        return companies
    raise ValueError(f"Unsupported company list type '{suffix}'. Use .json, .csv or .txt.")


def _coerce(entry: dict | str) -> Company:
    """Normalize a raw entry into a Company, deriving missing fields where possible."""
    if isinstance(entry, str):
        entry = {"name": entry}

    name = (entry.get("name") or "").strip()
    if not name:
        raise ValueError(f"Company entry missing a name: {entry!r}")

    careers_url = (entry.get("careers_url") or entry.get("careersUrl") or "").strip()
    domain = (entry.get("domain") or "").strip()

    if careers_url and not domain:
        domain = urlparse(careers_url).netloc
    if domain and not careers_url:
        careers_url = f"https://{domain}"
    if not careers_url and not domain:
        # Name-only entry (common for user-uploaded lists): let the search layer
        # discover the careers site by name, scoped away from aggregators.
        careers_url = ""
        domain = ""

    return Company(name=name, careers_url=careers_url, domain=domain)
