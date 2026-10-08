"""Fetches and cleans job-description text from a URL, with a paste fallback
for sites (LinkedIn, some ATS pages) that block simple scraping.
"""
import re
from dataclasses import dataclass

import requests
import trafilatura
from bs4 import BeautifulSoup

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MIN_JD_CHARS = 200

# Signatures of "the real content never made it into the HTML" pages — a
# JS-SPA shell, a bot-check, a login wall. If extracted text is short AND
# contains one of these, it's junk regardless of the char-count check.
_JUNK_MARKERS = (
    "enable javascript",
    "enable cookies",
    "javascript is disabled",
    "checking your browser",
    "just a moment",
    "verify you are a human",
    "please verify you are human",
    "access denied",
    "sign in to continue",
    "please sign in",
)


def _looks_like_junk(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _JUNK_MARKERS)


@dataclass
class JDResult:
    source: str          # the original URL or "(pasted text)"
    text: str
    ok: bool
    error: str = ""


def is_url(value: str) -> bool:
    return bool(_URL_RE.match(value.strip()))


def _bs4_fallback(html: str) -> str:
    """Crude but robust fallback for pages trafilatura can't parse (some ATS
    boilerplate/JSON-in-script pages confuse its boilerplate detector even
    when the HTML has plenty of real text)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _extract_best_text(html: str) -> str:
    """Runs trafilatura, falls back to a plain bs4 scrape if that comes back
    short — whichever yields more usable text."""
    extracted = trafilatura.extract(
        html, include_comments=False, include_tables=False, favor_recall=True
    ) or ""
    if len(extracted.strip()) < MIN_JD_CHARS:
        fallback_text = _bs4_fallback(html)
        if len(fallback_text.strip()) > len(extracted.strip()):
            extracted = fallback_text
    return extracted.strip()


def _is_usable(text: str) -> bool:
    if len(text) < MIN_JD_CHARS:
        return False
    # A junk marker in a genuinely long page is probably just a footer/cookie
    # banner; in a short page it's almost certainly the whole story.
    return not (_looks_like_junk(text) and len(text) < 1500)


def fetch_jd(url: str) -> JDResult:
    """Fetch a job posting URL and strip it to clean text. Returns ok=False
    (never raises) so the caller can fall back to a manual paste. Tries a
    plain HTTP fetch first, then a headless-browser render for pages that
    turn out to be JS-only shells."""
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=25, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
    except requests.RequestException as exc:
        html = ""
        static_fetch_error = f"Fetch failed: {exc}"
    else:
        static_fetch_error = ""

    extracted = _extract_best_text(html) if html else ""

    if not _is_usable(extracted):
        # Plain fetch got nothing real (JS-rendered page, bot check, etc.) —
        # try rendering it with a real (headless) browser instead.
        try:
            from job_apply_agent import browser_fetch

            rendered_html = browser_fetch.fetch_rendered_html(url)
            rendered_extracted = _extract_best_text(rendered_html)
            if _is_usable(rendered_extracted):
                return JDResult(source=url, text=rendered_extracted, ok=True)
            extracted = rendered_extracted or extracted
        except Exception as exc:
            if not extracted:
                return JDResult(
                    source=url, text="", ok=False,
                    error=static_fetch_error or f"Headless-browser fetch also failed: {exc}",
                )

    if not _is_usable(extracted):
        return JDResult(
            source=url,
            text=extracted or "",
            ok=False,
            error="Page fetched (including a rendered-browser attempt) but no real job "
            "description text was found — likely a login wall or bot check. Paste the JD "
            "text manually instead.",
        )
    return JDResult(source=url, text=extracted, ok=True)


def get_jd(url_or_text: str, pasted_fallback: str = "") -> JDResult:
    """Main entry point used by the pipeline. If url_or_text is a URL, try to
    fetch it; if that fails and pasted_fallback is provided, use that instead.
    If url_or_text is not a URL, treat it directly as pasted JD text."""
    value = url_or_text.strip()
    if not is_url(value):
        return JDResult(source="(pasted text)", text=value, ok=bool(value))

    result = fetch_jd(value)
    if not result.ok and pasted_fallback.strip():
        return JDResult(source=value, text=pasted_fallback.strip(), ok=True)
    return result
