"""Shared look and feel for the Streamlit pages: the stylesheet, small HTML
fragments (brand, status chips, run meter) and the readiness checks behind the
sidebar and the Setup page.

Anything that comes from outside the app (job titles and company names read
from web pages or written by the model, URLs) is HTML-escaped before it is put
in a fragment.
"""
from dataclasses import dataclass
from html import escape
from pathlib import Path

import requests
import streamlit as st

from job_apply_agent import config, local_settings

_CSS_FILE = Path(__file__).with_name("theme.css")
OLLAMA_PROBE_TIMEOUT_SECONDS = 1.5


# ----------------------------------------------------------------- readiness
@dataclass(frozen=True)
class Check:
    key: str
    label: str
    ok: bool
    detail: str


def readiness_checks(
    *,
    name: str,
    template_id: str,
    cv_text: str,
    placeholder_cv_text: str,
    credentials_exist: bool,
    token_exists: bool,
    ollama: str,
    model: str,
) -> list[Check]:
    """What still stands between a fresh install and a first generated application.

    `ollama` is one of "ready", "no_model" or "down" (see ollama_status)."""
    cv_is_real = bool(cv_text.strip()) and cv_text.strip() != placeholder_cv_text.strip()
    ollama_detail = {
        "ready": f"{model} is pulled",
        "no_model": f"{model} is not pulled yet",
        "down": "Ollama is not running",
    }[ollama]
    return [
        Check("name", "Your name", bool(name.strip()), name.strip() or "Not set"),
        Check("cv", "Your CV", cv_is_real, "Saved" if cv_is_real else "Still the placeholder"),
        Check("model", "AI model", ollama == "ready", ollama_detail),
        Check(
            "client", "Google client file", credentials_exist,
            "credentials.json found" if credentials_exist else "credentials.json missing",
        ),
        Check(
            "template", "Template document", bool(template_id.strip()),
            "ID saved" if template_id.strip() else "Not set",
        ),
        Check("login", "Google login", token_exists, "Connected" if token_exists else "Not connected"),
    ]


@st.cache_data(ttl=15, show_spinner=False)
def ollama_status(model: str) -> str:
    """"ready", "no_model" (running, model missing) or "down". Cached briefly so
    every page rerun does not hit the local server."""
    try:
        resp = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=OLLAMA_PROBE_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except requests.RequestException:
        return "down"
    names = {m.get("name") for m in resp.json().get("models", [])}
    return "ready" if model in names else "no_model"


def current_checks() -> list[Check]:
    settings = local_settings.load()
    cv_text = _read(config.CV_DUMP_FILE)
    return readiness_checks(
        name=settings["applicant_name"],
        template_id=settings["template_doc_id"],
        cv_text=cv_text,
        placeholder_cv_text=_read(config.CONTENT_TEMPLATE_DIR / "resume.md"),
        credentials_exist=config.GOOGLE_CREDENTIALS_FILE.exists(),
        token_exists=config.GOOGLE_TOKEN_FILE.exists(),
        ollama=ollama_status(settings["ollama_model"]),
        model=settings["ollama_model"],
    )


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


# ------------------------------------------------------------------ fragments
def chip(text: str, kind: str = "neutral") -> str:
    """A small status pill. kind: ok, fail, wait or neutral."""
    return f'<span class="chip chip-{escape(kind)}">{escape(text)}</span>'


def meter(completed: int, total: int, state: str) -> str:
    """The run progress bar. state: "running", "finished" or "interrupted"."""
    pct = 0 if total <= 0 else max(0, min(100, round(100 * completed / total)))
    noun = "posting" if total == 1 else "postings"
    label = {"running": "Running", "finished": "Finished", "interrupted": "Interrupted"}[state]
    return (
        f'<div class="meter meter-{escape(state)}">'
        f'<div class="meter-label"><strong>{label}</strong> {completed} of {total} {noun} done</div>'
        f'<div class="meter-track"><div class="meter-fill" style="width:{pct}%"></div></div>'
        f"</div>"
    )


def page_header(title: str, lede: str) -> None:
    st.html(f'<div class="page-head"><h1>{escape(title)}</h1><p>{escape(lede)}</p></div>')


def apply_theme() -> None:
    st.html(f"<style>{_CSS_FILE.read_text(encoding='utf-8')}</style>")


def sidebar_brand() -> None:
    st.html(
        '<div class="brand"><span class="brand-mark" aria-hidden="true"></span>'
        '<div><div class="brand-name">Job Application Agent</div>'
        '<div class="brand-sub">Tailored CVs and cover letters, drafted on this computer</div></div></div>'
    )


def sidebar_status(checks: list[Check]) -> None:
    """One line when everything is ready; otherwise only what is still missing."""
    todo = [c for c in checks if not c.ok]
    if not todo:
        st.html(
            '<div class="status"><div class="status-head"><span class="dot dot-ok"></span>Ready to generate</div></div>'
        )
        return
    rows = "".join(
        f'<div class="status-row"><span class="dot dot-wait"></span>'
        f'<span class="status-label">{escape(c.label)}</span>'
        f'<span class="status-detail">{escape(c.detail)}</span></div>'
        for c in todo
    )
    headline = f"{len(checks) - len(todo)} of {len(checks)} setup steps done"
    st.html(f'<div class="status"><div class="status-head">{escape(headline)}</div>{rows}</div>')


def checks_row(checks: list[Check]) -> None:
    """The readiness list at the top of the Setup page."""
    items = "".join(
        f'<div class="check">{chip("Ready" if c.ok else "To do", "ok" if c.ok else "wait")}'
        f'<span class="check-label">{escape(c.label)}</span>'
        f'<span class="check-detail">{escape(c.detail)}</span></div>'
        for c in checks
    )
    st.html(f'<div class="checks">{items}</div>')
