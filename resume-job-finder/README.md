# resume-job-finder

A CLI that reads your resume, understands your profile, and finds matching
openings **only on top companies' own career portals** — never on aggregators
like LinkedIn, Naukri, or Indeed.

## How it works

```
resume ─▶ parse ─▶ Claude: extract profile ─▶ search each company's careers site
                                                   (Tavily, aggregators excluded)
                                                          │
                          ranked matches ◀── Claude: score fit vs your resume
```

1. **Parse** your resume (`.pdf` / `.docx` / `.txt`).
2. **Analyze** it with Claude into a structured profile (roles, seniority, skills, keywords).
3. **Search** each company from a curated top-companies list, scoped to that
   company's own careers domain. Job aggregators and ATS hosts are excluded.
4. **Match** the findings against your resume with Claude, scored 0–100.
5. **Report** to the terminal as a ranked table, then let you **browse
   interactively** (view full details, open a listing in your browser), and
   optionally save to Markdown / JSON.

ATS-hosted listings (Greenhouse, Lever, Workday, etc.) are kept — they are the
company's real application flow. Only pure aggregators (LinkedIn, Naukri,
Indeed, …) are excluded.

Only **public, official channels** are surfaced (careers page, published
recruiting email, application link) — no scraping of individuals' personal
contact details.

## Setup

```bash
cd resume-job-finder
python -m venv .venv && . .venv/Scripts/activate   # Windows (Git Bash)
pip install -r requirements.txt

cp .env.example .env    # add TAVILY_API_KEY + your chosen LLM key (see below)
```

### LLM provider

Resume analysis and matching run on either **Anthropic (Claude)** or **Google
(Gemini)** — pick with `RJF_PROVIDER` in `.env` or `--provider` on the command
line. Tavily powers the web search for both.

| Provider | Env key | Get one at | Default model |
| --- | --- | --- | --- |
| `anthropic` (default) | `ANTHROPIC_API_KEY` | https://console.anthropic.com/ | `claude-opus-4-8` |
| `gemini` | `GEMINI_API_KEY` | https://aistudio.google.com/apikey | `gemini-2.5-pro` |

You only need the key for the provider you use. Switch per-run without editing
`.env`:

```bash
python -m resume_job_finder.cli find --resume cv.pdf --country in --provider gemini
```

## Usage

```bash
# Interactive (prompts for anything missing)
python -m resume_job_finder.cli find

# Fully specified
python -m resume_job_finder.cli find \
  --resume ./my_resume.pdf \
  --country in \
  --state Karnataka \
  --output reports/matches.md

# Use your own company list instead of the bundled one
python -m resume_job_finder.cli find --resume cv.pdf --companies my_top_companies.csv

# Skip the interactive browser (e.g. for scripts / CI)
python -m resume_job_finder.cli find --resume cv.pdf --country in -o out.md --no-interactive

# See what would run without spending any API calls
python -m resume_job_finder.cli find --resume cv.pdf --country us --dry-run

# List bundled country lists
python -m resume_job_finder.cli countries
```

If installed as a package (`pip install -e .`), the `rjf` command is available:
`rjf find --resume cv.pdf --country in`.

## Company lists

"Top companies in a country" includes **foreign MNCs operating there** (e.g.
Google, Amazon, Goldman Sachs in India), not only locally-headquartered firms.
**Product-based companies are listed first**, because the list is searched
top-down and `--max-companies` caps from the top — so order = priority.
Searches are scoped to the chosen country/state, so an MNC's global careers
site surfaces its *local* roles.

- **Bundled:** `data/companies/<code>.json` (e.g. `in.json`, `us.json`), each
  with ~100 top companies and their careers domains, product companies first.
  Extend or edit by adding entries:
  ```json
  { "name": "Company", "careers_url": "https://careers.company.com/", "domain": "careers.company.com" }
  ```
  `domain` is what scopes the search to that company's own site.
- **User-supplied:** pass `--companies` a `.json`, `.csv` (columns:
  `name,careers_url,domain`), or `.txt` (one company name per line). Name-only
  entries are searched by name with aggregators excluded.

## Configuration

| Env var | Purpose | Default |
| --- | --- | --- |
| `RJF_PROVIDER` | LLM provider: `anthropic` \| `gemini` | `anthropic` |
| `ANTHROPIC_API_KEY` | Analysis + matching (anthropic) | required for anthropic |
| `GEMINI_API_KEY` | Analysis + matching (gemini) | required for gemini |
| `TAVILY_API_KEY` | Scoped web search (both providers) | — (required) |
| `RJF_MODEL` | Claude model | `claude-opus-4-8` |
| `RJF_GEMINI_MODEL` | Gemini model | `gemini-2.5-pro` |
| `RJF_EFFORT` | Anthropic effort for resume analysis (`low`–`max`) | `high` |
| `RJF_MATCH_EFFORT` | Anthropic effort for matching (lighter = faster) | `medium` |
| `RJF_TIMEOUT` | Per-LLM-request timeout (seconds) | `180` |
| `RJF_MAX_LISTINGS` | Max de-duplicated listings sent to the matcher | `120` |

> **If a run seems stuck at "Matching openings…":** the matcher makes one LLM
> call over all collected listings. It now shows elapsed time, de-duplicates and
> caps listings (`RJF_MAX_LISTINGS`), uses lighter effort (`RJF_MATCH_EFFORT`),
> and times out after `RJF_TIMEOUT`s. To go faster, run with fewer companies
> (`--max-companies 20`) or a lighter model.

## Specific postings vs. landing pages

By default the tool returns **individual job postings** (URLs with a
requisition id or a posting slug) and drops careers home/search/landing pages.
If a company's site renders its jobs via JavaScript, search engines can't index
the individual postings — so you may get few or no results for it. In that case:

- run with `--allow-listings` to include careers/landing pages as a fallback, or
- lean on companies whose postings *are* indexable (ATS-hosted ones — Greenhouse,
  Lever, Workday — expose clean per-posting URLs).

## Notes & limits

- Results depend on what each careers site exposes to search; JS-rendered
  portals may return only a landing page (see above).
- Respect each site's terms of service and `robots.txt`. This tool queries a
  search API rather than crawling sites directly.
- Excluded domains are configurable in `src/resume_job_finder/config.py`.
