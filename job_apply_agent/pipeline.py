"""Orchestrates one job application end to end, and loops over a batch (e.g.
the up-to-10 links you paste into Streamlit or the CLI in one go).
"""
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from job_apply_agent import company_research, docs_writer, jd_extractor, llm

log = logging.getLogger(__name__)


@dataclass
class JobInput:
    url_or_text: str
    company_name: str = ""        # optional override; guessed if blank
    pasted_jd_fallback: str = ""  # used only if the URL fetch fails


@dataclass
class JobResult:
    job: JobInput
    ok: bool
    company: str = ""
    job_title: str = ""
    doc_url: str = ""
    error: str = ""
    jd_source: str = ""
    tailored_cv: str = ""
    cover_letter: str = ""
    log: list[str] = field(default_factory=list)


def run_job(job: JobInput, *, google_clients: docs_writer.GoogleClients | None = None) -> JobResult:
    result = JobResult(job=job, ok=False)

    jd = jd_extractor.get_jd(job.url_or_text, pasted_fallback=job.pasted_jd_fallback)
    result.jd_source = jd.source
    if not jd.ok or not jd.text.strip():
        result.error = jd.error or "No JD text available (fetch failed and no pasted fallback given)."
        return result
    result.log.append(f"JD extracted from {jd.source} ({len(jd.text)} chars)")

    meta = llm.extract_job_meta(jd.text, company_override=job.company_name)
    company = meta["company"]
    result.company = company
    result.job_title = meta["job_title"]
    result.log.append(f"Identified: {meta['job_title']} at {company}")

    research = company_research.research_company(company)
    research_block = research.as_prompt_block()
    result.log.append(f"Company research: {len(research.passages)} passage(s) gathered")

    try:
        tailored_cv = llm.generate_cv(company=company, jd_text=jd.text, research_block=research_block)
        result.tailored_cv = tailored_cv
        result.log.append("Tailored CV generated")

        cover_letter = llm.generate_cover_letter(
            company=company, jd_text=jd.text, research_block=research_block, tailored_cv=tailored_cv,
        )
        result.cover_letter = cover_letter
        result.log.append("Cover letter generated")
    except llm.OllamaError as exc:
        result.error = str(exc)
        return result

    try:
        clients = google_clients or docs_writer.get_clients()
        result.doc_url = docs_writer.create_application_doc(
            clients,
            company=company,
            job_title=result.job_title,
            cv_text=tailored_cv,
            cover_letter_text=cover_letter,
        )
        result.log.append(f"Google Doc created: {result.doc_url}")
    except Exception as exc:  # surfaced to the UI; generation itself still succeeded
        log.exception("Google Docs write failed for %s", job.url_or_text)
        result.error = f"Doc generated but Google Docs write failed: {exc}"
        return result

    result.ok = True
    return result


def run_batch(
    jobs: list[JobInput], on_result: Callable[[int, JobResult], None] | None = None
) -> list[JobResult]:
    """Runs jobs sequentially (Ollama is a single local model, so
    parallelising generation wouldn't be faster) and authenticates with Google
    once, reusing the client across all jobs.

    A crash inside one job is recorded as that job's error and the batch moves
    on, so one bad link can't take the other nine down with it.

    on_result(idx, result), if given, is called immediately after each job
    finishes. The Streamlit UI uses it to persist progress to disk as it
    happens, rather than only at the very end."""
    results: list[JobResult] = []
    google_clients = None
    try:
        google_clients = docs_writer.get_clients()
    except Exception as exc:
        # Each job retries the connection and reports its own error if it recurs.
        log.warning("Could not authenticate with Google up front: %s", exc)

    for idx, job in enumerate(jobs):
        try:
            result = run_job(job, google_clients=google_clients)
        except Exception as exc:
            log.exception("Unexpected failure in job %d (%s)", idx, job.url_or_text)
            result = JobResult(job=job, ok=False, error=f"Unexpected error: {exc}")
        results.append(result)
        if on_result:
            on_result(idx, result)
    return results
