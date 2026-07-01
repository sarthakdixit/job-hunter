"""Command-line interface for resume-job-finder."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from . import companies as companies_mod
from . import report
from .analyzer import analyze_resume
from .config import Settings, country_label
from .llm import LLMTimeoutError
from .matcher import match_jobs
from .models import Company
from .resume_parser import parse_resume
from .search import SearchError, SearchHit, make_client, search_company

app = typer.Typer(add_completion=False, help=__doc__)
console = Console()


@app.command()
def find(
    resume: Path = typer.Option(
        None, "--resume", "-r", help="Path to resume (.pdf/.docx/.txt)", exists=False
    ),
    country: str = typer.Option(None, "--country", "-c", help="Country code, e.g. in, us"),
    state: str = typer.Option(None, "--state", "-s", help="State/region (optional)"),
    provider: str = typer.Option(
        None, "--provider", "-p", help="LLM provider: anthropic | gemini (default from env)"
    ),
    companies: Path = typer.Option(
        None, "--companies", help="Your own company list (.json/.csv/.txt)"
    ),
    max_companies: int = typer.Option(100, "--max-companies", help="Cap companies searched"),
    per_company: int = typer.Option(5, "--per-company", help="Results per company"),
    postings_only: bool = typer.Option(
        True,
        "--postings-only/--allow-listings",
        help="Keep only specific job postings, not careers landing pages",
    ),
    fetch_pages: bool = typer.Option(
        True,
        "--fetch-pages/--no-fetch-pages",
        help="If search finds too few postings, mine the careers page + ATS boards",
    ),
    min_score: int = typer.Option(60, "--min-score", help="Minimum fit score (0-100)"),
    top_n: int = typer.Option(25, "--top", help="Max matches to return"),
    output: Path = typer.Option(None, "--output", "-o", help="Save report (.md or .json)"),
    interactive: bool = typer.Option(
        True, "--interactive/--no-interactive", help="Browse matches interactively after the run"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan and cost, don't run"),
) -> None:
    """Analyze a resume and find matching roles on top companies' career portals."""
    # --- Interactive fallbacks for the essentials ---
    if resume is None:
        resume = Path(typer.prompt("Path to your resume (.pdf/.docx/.txt)"))
    if country is None and companies is None:
        avail = ", ".join(companies_mod.available_countries()) or "(none bundled)"
        country = typer.prompt(f"Country code [{avail}]")

    try:
        settings = Settings.load(provider=provider)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    # --- Resolve the company set ---
    try:
        company_list = _resolve_companies(companies, country)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    # Location hint scopes searches to a region (state + country name).
    loc_parts = [p for p in (state, country_label(country)) if p]
    location_hint = ", ".join(loc_parts) or None
    if location_hint:
        console.print(f"[dim]Scoping job search to: {location_hint}[/]")
    company_list = company_list[:max_companies]

    console.print(f"[dim]LLM provider: {settings.provider} ({settings.model})[/]")

    if dry_run:
        est = len(company_list) * per_company
        console.print(
            f"[bold]Dry run[/]: would search [cyan]{len(company_list)}[/] companies, "
            f"up to [cyan]{est}[/] search results, then 2 {settings.provider} calls "
            f"(analyze + match). No API calls made."
        )
        raise typer.Exit(0)

    # --- 1. Parse + analyze the resume ---
    try:
        resume_text = parse_resume(resume)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    try:
        with console.status(f"[bold]Analyzing resume with {settings.provider}..."):
            profile = analyze_resume(resume_text, settings)
    except LLMTimeoutError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)
    report.print_profile(console, profile)

    # --- 2. Search each company's career portal (concurrently) ---
    client = make_client(settings)
    hits: list[SearchHit] = []
    failures = 0
    with Progress(
        TextColumn("[bold]Searching career portals"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("search", total=len(company_list))
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {
                pool.submit(
                    search_company,
                    client,
                    profile,
                    c,
                    per_company,
                    location_hint,
                    postings_only,
                    fetch_pages,
                ): c
                for c in company_list
            }
            for fut in as_completed(futures):
                try:
                    hits.extend(fut.result())
                except SearchError:
                    failures += 1
                finally:
                    progress.advance(task)

    kind = "specific postings" if postings_only else "listings"
    console.print(
        f"[dim]Collected {len(hits)} {kind} from {len(company_list)} companies"
        + (f" ({failures} search errors)" if failures else "")
        + "[/]"
    )

    # --- 3. Rank against the resume ---
    if not hits:
        console.print("[yellow]No specific postings were found on the searched portals.[/]")
        if postings_only:
            console.print(
                "[yellow]Many career sites render jobs via JavaScript, which search "
                "engines don't index. Re-run with [bold]--allow-listings[/bold] to include "
                "careers pages, or narrow with fewer, ATS-based companies.[/]"
            )
        raise typer.Exit(0)

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]Matching openings to your profile"),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("match", total=None)
            matches, sent = match_jobs(profile, hits, settings, min_score=min_score, top_n=top_n)
    except LLMTimeoutError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1)

    console.print(f"[dim]Ranked {sent} unique listings with {settings.provider}.[/]")
    report.print_matches(console, matches)

    # --- 4. Save + browse ---
    if output:
        if output.suffix.lower() == ".json":
            saved = report.save_json(output, profile, matches)
        else:
            saved = report.save_markdown(output, profile, matches)
        console.print(f"[green]Saved report to {saved}[/]")

    if interactive and matches and sys.stdin.isatty() and sys.stdout.isatty():
        report.browse_matches(console, matches)


@app.command("countries")
def list_countries() -> None:
    """List bundled country codes with curated company lists."""
    codes = companies_mod.available_countries()
    console.print("Bundled country lists: " + (", ".join(codes) or "(none)"))


def _resolve_companies(companies: Path | None, country: str | None) -> list[Company]:
    if companies is not None:
        return companies_mod.load_user_list(companies)
    if country:
        return companies_mod.load_curated(country)
    raise ValueError("Provide either --country or --companies.")


if __name__ == "__main__":
    app()
