"""Browser-rendered posting extraction (optional Playwright fallback).

Some career sites render their listings entirely client-side, so neither web
search nor a static HTML fetch sees the individual postings. This module drives
a headless Chromium via Playwright to render the page, then reuses the shared
HTML extraction logic on the rendered DOM.

Playwright is an optional dependency. If it is not installed, `renderer()`
raises RenderUnavailable with install instructions; callers degrade gracefully.
"""

from __future__ import annotations

from contextlib import contextmanager

from .extractor import extract_from_html
from .models import Company
from .search import SearchHit

_UA = "Mozilla/5.0 (compatible; resume-job-finder/0.1)"


class RenderUnavailable(RuntimeError):
    """Raised when Playwright (or its browser) is not installed."""


class BrowserRenderer:
    """Wraps a single headless browser; render one careers page at a time."""

    def __init__(self, page_timeout: float = 30.0) -> None:
        self._page_timeout_ms = int(page_timeout * 1000)
        self._pw = None
        self._browser = None
        self._context = None

    def start(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # noqa: F841
            raise RenderUnavailable(
                "Playwright is not installed. Install it with:\n"
                '    python -m pip install -e ".[render]"\n'
                "    python -m playwright install chromium"
            ) from exc

        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(headless=True)
        except Exception as exc:  # noqa: BLE001 - browser binary likely missing
            self._pw.stop()
            self._pw = None
            raise RenderUnavailable(
                "Chromium is not installed for Playwright. Run:\n"
                "    python -m playwright install chromium"
            ) from exc
        self._context = self._browser.new_context(user_agent=_UA)

    def stop(self) -> None:
        for closer in (self._context, self._browser):
            try:
                if closer is not None:
                    closer.close()
            except Exception:  # noqa: BLE001
                pass
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
        self._context = self._browser = self._pw = None

    def postings(
        self, company: Company, location: str | None, max_results: int
    ) -> list[SearchHit]:
        """Render the company's careers page and extract postings from the DOM."""
        if not company.careers_url or self._context is None:
            return []
        page = self._context.new_page()
        try:
            page.goto(company.careers_url, wait_until="networkidle", timeout=self._page_timeout_ms)
            html = page.content()
        except Exception:  # noqa: BLE001 - navigation/timeout: give up on this site
            return []
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
        return extract_from_html(company, html, company.careers_url, location, max_results)


@contextmanager
def renderer(page_timeout: float = 30.0):
    """Context manager yielding a started BrowserRenderer, cleaned up on exit."""
    br = BrowserRenderer(page_timeout=page_timeout)
    br.start()
    try:
        yield br
    finally:
        br.stop()
