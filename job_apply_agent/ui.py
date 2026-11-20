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

from job_apply_agent import config, local_settings, profiles

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
    cv_flows_ready: list[str],
    total_flows: int,
    regions_ready: bool,
    credentials_exist: bool,
    google_login: str,
    ollama: str,
    model: str,
) -> list[Check]:
    """What still stands between a fresh install and a first generated application.

    `cv_flows_ready` lists the flows whose CV is no longer the placeholder; one
    is enough to generate. `ollama` is "ready", "no_model" or "down"."""
    n_ready = len(cv_flows_ready)
    cv_detail = (
        f"{n_ready} of {total_flows} flows ready" if n_ready else "Still the placeholder"
    )
    ollama_detail = {
        "ready": f"{model} is pulled",
        "no_model": f"{model} is not pulled yet",
        "down": "Ollama is not running",
    }[ollama]
    return [
        Check("name", "Your name", bool(name.strip()), name.strip() or "Not set"),
        Check("cv", "Your CVs", n_ready > 0, cv_detail),
        Check(
            "regions", "Contact details", regions_ready,
            "Location and phone set" if regions_ready else "Add a location and phone for each region",
        ),
        Check("model", "AI model", ollama == "ready", ollama_detail),
        Check(
            "client", "Google client file", credentials_exist,
            "credentials.json found" if credentials_exist else "credentials.json missing",
        ),
        Check(
            "template", "Template document", bool(template_id.strip()),
            "ID saved" if template_id.strip() else "Not set",
        ),
        Check("login", "Google login", google_login == "connected", {
            "connected": "Connected",
            "expired": "Expired: reconnect on Setup",
            "missing": "Not connected",
        }[google_login]),
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


@st.cache_data(ttl=300, show_spinner=False)
def google_login_status() -> str:
    """Cached: checking can mean a round trip to Google's token endpoint."""
    from job_apply_agent import docs_writer  # Google client libraries are slow to import

    return docs_writer.login_status()


def flows_with_real_cv() -> list[str]:
    """Flows whose master CV has been edited away from the content.example placeholder."""
    ready = []
    for flow in profiles.FLOWS:
        text = _read(profiles.flow_dir(flow) / "resume.md").strip()
        placeholder = _read(config.CONTENT_TEMPLATE_DIR / flow / "resume.md").strip()
        if text and text != placeholder:
            ready.append(flow)
    return ready


def current_checks() -> list[Check]:
    settings = local_settings.load()
    regions = profiles.regions()
    return readiness_checks(
        name=settings["applicant_name"],
        template_id=settings["template_doc_id"],
        cv_flows_ready=flows_with_real_cv(),
        total_flows=len(profiles.FLOWS),
        regions_ready=bool(regions) and all(r.location and r.phone for r in regions.values()),
        credentials_exist=config.GOOGLE_CREDENTIALS_FILE.exists(),
        google_login=google_login_status(),
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
