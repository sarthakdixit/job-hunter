"""Render results to the terminal and to saveable files (Markdown / JSON)."""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .models import JobMatch, ResumeProfile


def print_profile(console: Console, profile: ResumeProfile) -> None:
    console.print()
    console.rule("[bold]Resume profile")
    console.print(f"[bold]Name:[/] {profile.full_name or '—'}")
    console.print(f"[bold]Target roles:[/] {', '.join(profile.target_roles) or '—'}")
    console.print(f"[bold]Seniority:[/] {profile.seniority}")
    if profile.years_experience is not None:
        console.print(f"[bold]Experience:[/] ~{profile.years_experience:g} yrs")
    console.print(f"[bold]Top skills:[/] {', '.join(profile.skills[:12]) or '—'}")
    console.print(f"[bold]Summary:[/] {profile.summary or '—'}")


def print_matches(console: Console, matches: list[JobMatch]) -> None:
    console.print()
    console.rule(f"[bold]Matches ({len(matches)})")
    if not matches:
        console.print("[yellow]No matching openings found on the searched portals.[/]")
        return

    table = Table(show_lines=True, expand=True)
    table.add_column("#", justify="right", width=3)
    table.add_column("Fit", justify="right", width=4)
    table.add_column("Company", width=18)
    table.add_column("Role", width=28)
    table.add_column("Where to apply", overflow="fold")

    for i, m in enumerate(matches, start=1):
        apply = m.apply_url or m.url
        contact_bits = [b for b in (m.careers_email, m.company_linkedin) if b]
        contact = ("\n" + " · ".join(contact_bits)) if contact_bits else ""
        loc = f"\n[dim]{m.location}[/]" if m.location else ""
        table.add_row(
            str(i),
            _score_style(m.fit_score),
            m.company,
            m.title,
            f"[link={apply}]{apply}[/link]{loc}{contact}",
        )
    console.print(table)


def browse_matches(console: Console, matches: list[JobMatch]) -> None:
    """Interactive loop: inspect a match's details or open it in the browser."""
    if not matches:
        return
    console.print(
        "\n[dim]Interactive — enter a [bold]#[/bold] for full details, "
        "[bold]o<#>[/bold] to open in your browser (e.g. [bold]o3[/bold]), "
        "or [bold]Enter[/bold]/[bold]q[/bold] to finish.[/]"
    )
    while True:
        choice = Prompt.ask("[bold cyan]select[/]", default="q", show_default=False).strip().lower()
        if choice in ("", "q", "quit", "exit"):
            break

        open_in_browser = choice.startswith("o")
        num = choice[1:].strip() if open_in_browser else choice
        if not num.isdigit():
            console.print("[red]Enter a match number, e.g. 3 or o3.[/]")
            continue
        idx = int(num) - 1
        if not (0 <= idx < len(matches)):
            console.print(f"[red]Pick a number between 1 and {len(matches)}.[/]")
            continue

        m = matches[idx]
        apply = m.apply_url or m.url
        if open_in_browser:
            webbrowser.open(apply)
            console.print(f"[green]Opening {apply}[/]")
            continue
        console.print(_detail_panel(idx + 1, m))


def _detail_panel(number: int, m: JobMatch) -> Panel:
    apply = m.apply_url or m.url
    lines = [
        f"[bold]{m.title}[/]  —  {m.company}",
        f"[bold]Fit:[/] {_score_style(m.fit_score)}",
    ]
    if m.location:
        lines.append(f"[bold]Location:[/] {m.location}")
    lines.append(f"[bold]Apply:[/] [link={apply}]{apply}[/link]")
    if m.careers_email:
        lines.append(f"[bold]Careers email:[/] {m.careers_email}")
    if m.company_linkedin:
        lines.append(f"[bold]Company LinkedIn:[/] {m.company_linkedin}")
    if m.reasoning:
        lines.append(f"\n[bold]Why it fits:[/]\n{m.reasoning}")
    return Panel("\n".join(lines), title=f"Match #{number}", border_style="cyan")


def _score_style(score: int) -> str:
    color = "green" if score >= 80 else "yellow" if score >= 65 else "white"
    return f"[{color}]{score}[/]"


def save_json(path: str | Path, profile: ResumeProfile, matches: list[JobMatch]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "profile": profile.model_dump(),
        "matches": [m.model_dump() for m in matches],
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def save_markdown(path: str | Path, profile: ResumeProfile, matches: list[JobMatch]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Job matches for {profile.full_name or 'candidate'}",
        "",
        f"**Target roles:** {', '.join(profile.target_roles) or '—'}  ",
        f"**Seniority:** {profile.seniority}  ",
        f"**Top skills:** {', '.join(profile.skills[:12]) or '—'}",
        "",
        f"## Matches ({len(matches)})",
        "",
        "| Fit | Company | Role | Apply | Contact |",
        "| --- | --- | --- | --- | --- |",
    ]
    for m in matches:
        apply = m.apply_url or m.url
        contact = " · ".join(b for b in (m.careers_email, m.company_linkedin) if b) or "—"
        title = m.title.replace("|", "\\|")
        lines.append(
            f"| {m.fit_score} | {m.company} | {title} | [link]({apply}) | {contact} |"
        )
    lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p
