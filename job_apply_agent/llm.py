"""Thin client for a local Ollama model, plus the two prompt assemblies
(tailored CV, then cover letter) built from prompts.md + your CV dump.
"""
import logging
import re
from pathlib import Path

import requests

from job_apply_agent import config
from job_apply_agent.prompt_loader import load_prompts

log = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


# Ollama defaults to a small context window (often 2048-4096 tokens)
# regardless of what the model itself supports. Our real prompts (CV dump +
# JD + company research + a reference letter) can easily run past that, which
# silently truncates the *input* and leaves little/no room for output;
# the model then returns an empty or near-empty response with no error.
# So we size num_ctx to the actual prompt every call, and hard-fail (rather
# than silently accept) if the response still comes back too short.
MIN_OUTPUT_CHARS = 400
CHARS_PER_TOKEN_ESTIMATE = 3  # deliberately conservative (overestimates tokens)
MIN_NUM_CTX = 8192
MAX_NUM_CTX = 32768
RESERVED_OUTPUT_TOKENS = 2000

CV_ATTEMPTS = 2
COVER_LETTER_ATTEMPTS = 3


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN_ESTIMATE)


def _context_size_for(prompt: str) -> int:
    needed = _estimate_tokens(prompt) + RESERVED_OUTPUT_TOKENS
    return min(MAX_NUM_CTX, max(MIN_NUM_CTX, needed))


def _call_ollama(prompt: str, *, model: str, num_ctx: int) -> dict:
    try:
        resp = requests.post(
            f"{config.OLLAMA_HOST}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                # qwen3.5 is a thinking/reasoning model: with thinking left on it
                # generates a large hidden chain-of-thought first, which on CPU can
                # run for a very long time before any real output appears. We just
                # want the direct answer, so turn it off.
                "think": False,
                "options": {"num_ctx": num_ctx, "num_predict": -1},
            },
            timeout=config.OLLAMA_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(
            f"Could not reach Ollama at {config.OLLAMA_HOST}. Is 'ollama serve' running "
            f"and is the model pulled ('ollama pull {model}')? Details: {exc}"
        ) from exc

    data = resp.json()
    if data.get("error"):
        raise OllamaError(f"Ollama returned an error: {data['error']}")
    return data


def generate(prompt: str, *, model: str | None = None, min_output_chars: int = MIN_OUTPUT_CHARS) -> str:
    model = model or config.OLLAMA_MODEL
    num_ctx = _context_size_for(prompt)

    data = _call_ollama(prompt, model=model, num_ctx=num_ctx)
    text = data.get("response", "").strip()

    if len(text) < min_output_chars and num_ctx < MAX_NUM_CTX:
        # Most likely cause: context was still too tight. Retry once with the
        # window maxed out before giving up.
        log.info("Short response (%d chars) at num_ctx=%d; retrying at %d", len(text), num_ctx, MAX_NUM_CTX)
        num_ctx = MAX_NUM_CTX
        data = _call_ollama(prompt, model=model, num_ctx=num_ctx)
        text = data.get("response", "").strip()

    if len(text) < min_output_chars:
        raise OllamaError(
            f"Model returned only {len(text)} chars, which is too short (expected at least "
            f"{min_output_chars}). Estimated prompt size ~{_estimate_tokens(prompt)} tokens against "
            f"num_ctx={num_ctx}, done_reason={data.get('done_reason')!r}. This usually means "
            f"the model choked on/refused the prompt rather than a context problem at this "
            f"point. Check 'ollama serve' output, or try shortening your CV / cover letter "
            f"reference files in content/."
        )
    return text


def extract_job_meta(jd_text: str, *, company_override: str = "") -> dict:
    """Cheap, short LLM call to pull a clean company name + job title out of
    raw JD text, used for naming the generated doc. Never raises: falls back
    to safe defaults if Ollama is unavailable or the response is unparsable."""
    prompt = f"""Read this job posting text and extract two things: the company name
and the exact job title being advertised. Respond with EXACTLY two lines and
nothing else, no explanation:
COMPANY: <company name>
TITLE: <job title>
If either genuinely cannot be determined from the text, write Unknown for that line.

JOB POSTING TEXT:
{jd_text[:4000]}
"""
    company, title = "", ""
    try:
        text = generate(prompt, min_output_chars=5)
    except OllamaError as exc:
        log.warning("Job metadata extraction failed: %s", exc)
        text = ""

    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("COMPANY:"):
            company = line.split(":", 1)[1].strip()
        elif line.upper().startswith("TITLE:"):
            title = line.split(":", 1)[1].strip()

    if company_override.strip():
        company = company_override.strip()
    if not company or company.lower() == "unknown":
        company = "Unknown Company"
    if not title or title.lower() == "unknown":
        title = "Role"

    return {"company": company, "job_title": title}


def _read_content(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Missing content file {path}. Open the Setup page to create it, or copy the "
            f"matching file from content.example/."
        ) from exc


def _read_cv_dump() -> str:
    return _read_content(config.CV_DUMP_FILE)


def _read_cover_letter_reference() -> str:
    return _read_content(config.COVER_LETTER_REFERENCE_FILE)


def _read_project_notes() -> str:
    return _read_content(config.PROJECT_NOTES_FILE)


# A section heading in the master CV: optional markdown "#"s, optional "**"
# bold, then an ALL-CAPS title ("## **WORK EXPERIENCE**" or "WORK EXPERIENCE").
_CV_HEADING_RE = re.compile(r"^\s*(?:#{1,6}\s*)?(?:\*\*)?([A-Z][A-Z0-9 &,./'-]*?)(?:\*\*)?\s*$")


def cv_section_headings(cv_dump: str) -> list[str]:
    """The ALL-CAPS section headings of the master CV, in order. Read from the
    file rather than hardcoded, so adding a section (e.g. PROJECTS) to the CV
    is all it takes for the prompt to preserve it. The first non-blank line is
    the applicant's name, never a heading."""
    headings: list[str] = []
    lines = [ln for ln in cv_dump.splitlines() if ln.strip()]
    for line in lines[1:]:
        match = _CV_HEADING_RE.match(line)
        if match:
            heading = match.group(1).strip()
            if heading not in headings:
                headings.append(heading)
    return headings


def build_cv_prompt(*, company: str, jd_text: str, research_block: str) -> str:
    prompts = load_prompts()
    cv_dump = _read_cv_dump()
    project_notes = _read_project_notes()
    headings = cv_section_headings(cv_dump)
    heading_order = ", ".join(headings) if headings else "the headings that appear above"

    # prompts.md escapes brackets as \[RESUME\] / \[COMPANY\] for markdown rendering
    instructions = prompts.resume.replace("\\[COMPANY\\]", company or "the company")
    instructions = instructions.replace("[COMPANY]", company or "the company")
    instructions = instructions.replace("\\[RESUME\\]", "the CV provided below")
    instructions = instructions.replace("[RESUME]", "the CV provided below")

    return f"""{instructions}

{prompts.writing_style}

=== JOB DESCRIPTION ({company or "unknown company"}) ===
{jd_text}

=== COMPANY RESEARCH ===
{research_block}

=== MY CURRENT CV (this is the full source of truth: select and rewrite from this, never invent experience not present here) ===
{cv_dump}

=== ADDITIONAL PROJECT DETAIL (background only: mine this for accurate specifics to phrase bullets with, never copy its headings or paste it verbatim) ===
{project_notes}

STRUCTURE — follow this exactly: reproduce the same section headings, in the
same order, as MY CURRENT CV above: the name and contact line, then these
sections in this exact order: {heading_order}. Do not invent new headings,
merge sections, or reorder them. Only tailor the content and bullet selection
within each section. Never add a section that is not in that list (for
example a certificates section), even if you'd normally expect a CV to have
one. Write each
section heading in plain ALL CAPS on its own line, no markdown symbols around
it (not "## HEADING", not "**HEADING**", just HEADING), and no blank line
between a section's heading and the line before it. Go straight from the
last line of one section to the next section's heading with no extra blank
line above the heading.

LENGTH — this CV must fit on two printed pages. Be selective: for the two
most recent/relevant roles use up to 4 bullets, for every other role or
project use 2-3 bullets, and keep each bullet to one line of real content
(concise, no padding). Do not pad the professional summary beyond 2-3
sentences.

FORMATTING CONVENTION — this is parsed by code afterwards, so follow it
exactly, character for character:
- Every job/education/project entry is one line: "**Title**" (bold, markdown
  asterisks, nothing else inside the bold) immediately followed by
  " | Organisation, Location | Dates". Example:
  "**Job Title** | Organisation, Location | Mon YYYY - Mon YYYY"
  Never bold anything else on that line, and never bold a second segment on
  the same line.
- Every bullet line starts with "* " (asterisk, one space) followed by plain
  text with no bold, italics, or other markdown inside it at all.
- A "Tools/Skills: ..." line is plain text, no markdown.
Ignore the exact markdown style used in MY CURRENT CV below (it is
inconsistent); always output entries and bullets in the convention above
regardless of how the source is formatted.

CONTACT DETAILS — copy the name, location, email, phone number and links from
the contact line in MY CURRENT CV above exactly as written (keep links in
"[label](url)" markdown form). Never change, guess, or invent any of them.

THIS REQUEST IS FOR THE CV ONLY. A separate request will handle the cover
letter. Do not write one here, and do not append one after the CV even if
an earlier instruction mentioned producing "the resume and the cover
letter" as a pair; that referred to the two deliverables of the overall
application, not this single response. Stop writing as soon as the CV ends.
Output only the tailored CV text, nothing after it. No commentary, no
markdown code fences, no second document.
"""


def build_cover_letter_prompt(*, company: str, jd_text: str, research_block: str, tailored_cv: str) -> str:
    prompts = load_prompts()
    reference_letter = _read_cover_letter_reference()
    project_notes = _read_project_notes()
    first_name = config.APPLICANT_NAME.split()[0] if config.APPLICANT_NAME else "[Your first name]"

    return f"""{prompts.cover_letter}

{prompts.writing_style}

=== JOB DESCRIPTION ({company or "unknown company"}) ===
{jd_text}

=== COMPANY RESEARCH ===
{research_block}

=== MY TAILORED CV FOR THIS ROLE ===
{tailored_cv}

=== REFERENCE COVER LETTER (style/structure example only, not content to reuse) ===
{reference_letter}

=== ADDITIONAL PROJECT DETAIL (real, specific detail behind my CV bullets: use this to build genuine, concrete narrative rather than vague restatements of the CV. Never copy its headings or paste it verbatim, write it in your own words) ===
{project_notes}

STRUCTURE — follow this exactly: same opening line ("Dear Hiring Manager,"),
same paragraph structure and ordering as the reference letter above, and the
same sign-off (a line reading "Best," followed by "{first_name}" on its own line).
Match its tone and register. Only the content (which requirements you cover,
which examples you draw on, the narrative) should change, not the shape of
the letter.

CONTACT DETAILS — if you reference my name, location, email, phone or links,
copy them from MY TAILORED CV above exactly as written. Never change, guess,
or invent any of them.

THIS REQUEST IS FOR THE COVER LETTER ONLY. The CV above is reference
material, not something to reproduce. Do not repeat CV section headings
(PROFESSIONAL SUMMARY, WORK EXPERIENCE, etc.) or restate it in this
response, even if an earlier instruction mentioned producing "the resume and
the cover letter" as a pair; that referred to the two deliverables of the
overall application, not this single response. Output only the cover letter
text, nothing before or after it. No commentary, no markdown code fences, no
second document.
"""


_SUMMARY_HEADING_RE = re.compile(r"PROFESSIONAL SUMMARY", re.IGNORECASE)


def _real_cv_header() -> str:
    """The name + contact line from the real CV, lightly cleaned of markdown.
    Used to overwrite whatever header the model produced: LLMs have been
    observed inventing a plausible-looking but wrong phone number/location
    even when explicitly told not to, so this is enforced in code rather
    than left to prompt compliance."""
    cv_dump = _read_cv_dump()
    match = _SUMMARY_HEADING_RE.search(cv_dump)
    header_raw = cv_dump[: match.start()] if match else cv_dump.split("\n\n", 1)[0]

    lines = []
    for line in header_raw.splitlines():
        stripped = line.strip().lstrip("#").strip().replace("**", "").replace("__", "")
        if stripped:
            lines.append(stripped)
    return "\n".join(lines).strip()


def _enforce_real_contact_header(tailored_cv: str) -> str:
    real_header = _real_cv_header()
    match = _SUMMARY_HEADING_RE.search(tailored_cv)
    if not real_header or not match:
        return tailored_cv  # can't safely locate the split point; leave generated text as-is
    return f"{real_header}\n\n{tailored_cv[match.start():]}"


# Markers that mean the model bled the *other* document into this one
# (seen in practice: a "Dear Hiring Manager," cover letter appended after a
# CV, complete with invented contact details). Caught here so the pipeline
# fails loudly instead of writing contaminated content to the doc.
_COVER_LETTER_MARKERS = ("dear hiring manager", "dear hiring team", "yours sincerely")
_CV_SECTION_MARKERS = ("professional summary", "work experience", "technical skills")

# The Writing Style section in prompts.md explicitly bans these, but a local
# model won't always comply, so it's worth one extra regeneration attempt to avoid
# the most obvious AI-cliche tells, without hard-failing the whole job over
# a stylistic slip if it recurs.
_BANNED_PHRASES = (
    "hit the ground running", "leverage my skills", "leverage my", "seamlessly",
    "dynamic environment", "passionate about", "proven track record",
    "holistic approach", "cutting-edge", "robust solution",
)


def generate_cv(*, company: str, jd_text: str, research_block: str) -> str:
    prompt = build_cv_prompt(company=company, jd_text=jd_text, research_block=research_block)
    for _ in range(CV_ATTEMPTS):
        text = generate(prompt)
        if not any(marker in text.lower() for marker in _COVER_LETTER_MARKERS):
            return _enforce_real_contact_header(text)
    raise OllamaError(
        "Generated CV kept containing a cover letter bled in (found a salutation like "
        "'Dear Hiring Manager') even after retrying. Refusing to use this output."
    )


def generate_cover_letter(*, company: str, jd_text: str, research_block: str, tailored_cv: str) -> str:
    prompt = build_cover_letter_prompt(
        company=company, jd_text=jd_text, research_block=research_block, tailored_cv=tailored_cv
    )
    best_clean_attempt = None
    for _ in range(COVER_LETTER_ATTEMPTS):
        text = generate(prompt)
        if sum(marker in text.lower() for marker in _CV_SECTION_MARKERS) >= 2:
            continue  # CV bled in: never usable, always retry
        best_clean_attempt = text
        if not any(phrase in text.lower() for phrase in _BANNED_PHRASES):
            return text  # clean of both contamination and cliche tells
        # otherwise keep this as a fallback and try once more for a cleaner draft

    if best_clean_attempt is not None:
        return best_clean_attempt  # contamination-free but kept an AI-cliche phrase; still usable
    raise OllamaError(
        "Generated cover letter kept containing CV section headings bled in even after "
        "retrying. Refusing to use this output."
    )
