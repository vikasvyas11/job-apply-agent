"""Headless-browser fallback for job pages that are pure JS SPAs (Workday,
some Greenhouse/Lever embeds, LinkedIn's logged-out view, etc.) where a plain
requests.get() only ever returns an empty shell ("You need to enable
JavaScript to run this app."). Only used when the plain fetch fails or looks
like boilerplate — it's slower (a real Chromium launch) so it's the fallback,
not the first attempt.
"""
import contextlib

from playwright.sync_api import sync_playwright

from job_apply_agent.jd_extractor import USER_AGENT

RENDER_TIMEOUT_MS = 25_000


def fetch_rendered_html(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, timeout=RENDER_TIMEOUT_MS, wait_until="domcontentloaded")
            # some career pages never go fully idle (polling widgets etc.): use what we have
            with contextlib.suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=RENDER_TIMEOUT_MS)
            html = page.content()
        finally:
            browser.close()
    return html
