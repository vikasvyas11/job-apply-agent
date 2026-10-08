"""Free, no-API-key company research: DuckDuckGo search + a direct scrape of
the company's own site. Produces a handful of short, clean passages meant to
be dropped straight into the LLM prompt (not raw HTML/whole pages, to keep
inside a small local model's context window).
"""
import logging
from dataclasses import dataclass, field

import requests
import trafilatura

try:
    from ddgs import DDGS
except ImportError:  # older package name
    from duckduckgo_search import DDGS

from job_apply_agent.jd_extractor import USER_AGENT

log = logging.getLogger(__name__)

MAX_RESULTS_PER_QUERY = 3
MAX_CHARS_PER_PASSAGE = 1200
MIN_SCRAPED_CHARS = 150
MIN_SNIPPET_CHARS = 60


@dataclass
class ResearchResult:
    company: str
    passages: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)

    def as_prompt_block(self) -> str:
        if not self.passages:
            return "(No company research could be gathered automatically.)"
        blocks = [f"Source: {src}\n{passage}" for src, passage in zip(self.sources, self.passages, strict=True)]
        return "\n\n".join(blocks)


def _scrape(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return ""
    text = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
    return (text or "").strip()[:MAX_CHARS_PER_PASSAGE]


def research_company(company: str) -> ResearchResult:
    """Best-effort: any search failure just yields less (or no) research,
    because a job application shouldn't die over missing background."""
    result = ResearchResult(company=company)
    if not company.strip():
        return result

    queries = [
        f"{company} mission vision values about",
        f"{company} recent news",
        f"{company} product OR engineering blog",
    ]

    seen_urls: set[str] = set()
    try:
        with DDGS() as ddgs:
            for query in queries:
                try:
                    hits = list(ddgs.text(query, max_results=MAX_RESULTS_PER_QUERY))
                except Exception as exc:
                    log.warning("Search failed for %r: %s", query, exc)
                    continue
                for hit in hits:
                    url = hit.get("href") or hit.get("url")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    passage = _scrape(url)
                    if len(passage) < MIN_SCRAPED_CHARS:
                        # fall back to the search snippet itself, still useful signal
                        snippet = hit.get("body", "")
                        if len(snippet) < MIN_SNIPPET_CHARS:
                            continue
                        passage = snippet
                    result.passages.append(passage)
                    result.sources.append(url)
                    break  # one good passage per query is enough
    except Exception as exc:
        log.warning("Company research unavailable for %r: %s", company, exc)

    return result
