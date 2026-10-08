"""Applications page: queue up to 10 job links, run them in the background, review the drafts."""
import threading
from html import escape
from pathlib import Path

import streamlit as st

from job_apply_agent import config, run_store, ui
from job_apply_agent.pipeline import JobInput, JobResult, run_batch

N_SLOTS = 10
N_VISIBLE_SLOTS = 3
REFRESH_EVERY = "3s"


@st.cache_resource
def _worker_registry() -> dict:
    """Shared by every session for the life of the server process, so a second
    browser tab (or a double click) can't start a second batch that competes
    with the first for the single local Ollama model."""
    return {"thread": None, "run_dir": None}


def _result_to_dict(result: JobResult) -> dict:
    return {
        "url_or_text": result.job.url_or_text,
        "ok": result.ok,
        "company": result.company,
        "job_title": result.job_title,
        "doc_url": result.doc_url,
        "error": result.error,
        "jd_source": result.jd_source,
        "tailored_cv": result.tailored_cv,
        "cover_letter": result.cover_letter,
        "log": result.log,
    }


def _worker(jobs: list[JobInput], run_dir: Path) -> None:
    """Runs on a plain background thread owned by the Streamlit *server*
    process, so it keeps going to completion regardless of whether any browser
    tab is attached, reconnecting, or asleep."""

    def on_result(idx: int, result: JobResult) -> None:
        run_store.save_job_result(run_dir, idx, _result_to_dict(result))
        status = run_store.read_status(run_dir)
        status["completed"] = status.get("completed", 0) + 1
        run_store.write_status(run_dir, status)

    try:
        run_batch(jobs, on_result=on_result)
    except Exception as exc:
        # run_batch isolates per-job failures, so reaching here means a bug.
        # Record it instead of letting the thread vanish silently.
        for idx, job in enumerate(jobs):
            if not (run_dir / f"job_{idx}.json").exists():
                run_store.mark_job_failed(run_dir, idx, job.url_or_text, str(exc))
    finally:
        status = run_store.read_status(run_dir)
        status["done"] = True
        run_store.write_status(run_dir, status)


def _is_live(run_dir: Path) -> bool:
    registry = _worker_registry()
    thread = registry["thread"]
    return thread is not None and thread.is_alive() and registry["run_dir"] == run_dir


def _job_title(r: dict) -> str:
    if r["company"] or r["job_title"]:
        return f"{r['job_title'] or 'Role'} at {r['company']}"
    return r["url_or_text"]


def _render_job(run_dir: Path, idx: int, r: dict) -> None:
    kind = "ok" if r["ok"] else "fail"
    with st.container(border=True, key=f"sheet_{kind}_{run_dir.name}_{idx}"):
        head, action = st.columns([5, 1.4], vertical_alignment="center")
        head.html(
            f'<div class="sheet-head">{ui.chip("Done" if r["ok"] else "Failed", kind)}'
            f"<h3>{escape(_job_title(r))}</h3>"
            f'<p class="sheet-source">{escape(r["jd_source"] or r["url_or_text"])}</p></div>'
        )
        if r["ok"] and r["doc_url"]:
            action.link_button("Open Google Doc", r["doc_url"], type="primary")
        if not r["ok"]:
            st.error(r["error"])
        if r["log"]:
            with st.expander("Run log"):
                for line in r["log"]:
                    st.write(f"- {line}")
        if r["tailored_cv"] or r["cover_letter"]:
            tab_cv, tab_letter = st.tabs(["Tailored CV", "Cover letter"])
            with tab_cv:
                st.text_area(
                    "CV", r["tailored_cv"], height=420, key=f"cv_view_{run_dir.name}_{idx}",
                    label_visibility="collapsed",
                )
            with tab_letter:
                st.text_area(
                    "Cover Letter", r["cover_letter"], height=420, key=f"cl_view_{run_dir.name}_{idx}",
                    label_visibility="collapsed",
                )


def _run_view(run_dir: Path, was_running: bool) -> None:
    """The progress meter and the result sheets. Re-reads the run from disk on
    every call, so it can be refreshed on a timer while the batch is running."""
    status = run_store.read_status(run_dir)
    n_jobs = status.get("n_jobs", 0)
    completed = status.get("completed", 0)
    done = status.get("done", False)

    if was_running and done:
        st.rerun()  # full rerun: stops the timer and re-enables the Generate button

    state = "finished" if done else ("running" if _is_live(run_dir) else "interrupted")
    if n_jobs:
        st.html(ui.meter(completed, n_jobs, state))
    if state == "interrupted":
        st.caption("This run stopped before it finished, most likely because the app was restarted.")

    results = run_store.load_job_results(run_dir)
    if not results:
        st.caption("Nothing yet. The first job is probably still generating; a few minutes per job is normal.")
        return
    for idx in sorted(results):
        _render_job(run_dir, idx, results[idx])


def _render_run(run_dir: Path) -> None:
    status = run_store.read_status(run_dir)
    running = not status.get("done", False) and _is_live(run_dir)
    view = st.fragment(run_every=REFRESH_EVERY if running else None)(_run_view)
    view(run_dir, running)


# ------------------------------------------------------------------------ page
ui.page_header(
    "Applications",
    f"Paste up to {N_SLOTS} job links. Each one becomes a tailored CV and cover letter in a copy of your "
    f"Google Doc template, written by {config.OLLAMA_MODEL} on this computer.",
)

registry = _worker_registry()
busy = registry["thread"] is not None and registry["thread"].is_alive()
if busy:
    st.info("A batch is running. You can start another when it finishes.", icon=":material/hourglass_top:")

# Auto-resume: pick up the most recent run even after a full page/session reset.
if "active_run_dir" not in st.session_state:
    st.session_state.active_run_dir = run_store.get_current_run()


def _slot(i: int) -> tuple[str, str, str]:
    with st.container(key=f"slot_{i}"):
        num, fields = st.columns([0.35, 6], vertical_alignment="top")
        num.html(f'<div class="qnum">{i + 1}</div>')
        with fields:
            url_col, company_col = st.columns([3, 1.3])
            url = url_col.text_input(
                f"Job {i + 1} link", key=f"url_{i}", label_visibility="collapsed",
                placeholder="Link to the job posting",
            )
            company = company_col.text_input(
                f"Job {i + 1} company", key=f"company_{i}", label_visibility="collapsed",
                placeholder="Company (optional)",
            )
            with st.expander("Paste the job description instead"):
                st.caption("Use this when a link can't be fetched, for example LinkedIn pages that need a login.")
                pasted = st.text_area(
                    f"Job {i + 1} description", key=f"pasted_{i}", height=110, label_visibility="collapsed",
                    placeholder="Leave blank unless the link fails to load.",
                )
    return url, company, pasted


with st.form("jobs_form"):
    rows = [_slot(i) for i in range(N_VISIBLE_SLOTS)]
    more_in_use = any(st.session_state.get(f"url_{i}", "").strip() for i in range(N_VISIBLE_SLOTS, N_SLOTS))
    with st.expander(f"Add more jobs (up to {N_SLOTS - N_VISIBLE_SLOTS} more)", expanded=more_in_use):
        rows += [_slot(i) for i in range(N_VISIBLE_SLOTS, N_SLOTS)]

    action_col, hint_col = st.columns([1, 3], vertical_alignment="center")
    submitted = action_col.form_submit_button("Generate all", type="primary", disabled=busy)
    hint_col.caption(
        "Generation keeps running if you close this tab. Leave the terminal window that started the app open."
    )

if submitted:
    jobs = [
        JobInput(url_or_text=url.strip(), company_name=company.strip(), pasted_jd_fallback=pasted.strip())
        for url, company, pasted in rows
        if url.strip()
    ]
    if not jobs:
        st.warning("Add at least one job link first.")
    else:
        run_dir = run_store.new_run(len(jobs))
        thread = threading.Thread(target=_worker, args=(jobs, run_dir), daemon=True, name="batch-worker")
        registry["thread"] = thread
        registry["run_dir"] = run_dir
        thread.start()
        st.session_state.active_run_dir = run_dir
        st.rerun()

active = st.session_state.active_run_dir
if active:
    st.html('<h2 class="section-title">This run</h2>')
    _render_run(active)
else:
    st.caption("No runs yet. Add a job link above and choose Generate all.")

past_runs = [p for p in run_store.list_runs() if p != active]
if past_runs:
    with st.expander(f"Past runs ({len(past_runs)})"):
        for p in past_runs:
            status = run_store.read_status(p)
            label = f"{p.name}: {status.get('completed', 0)}/{status.get('n_jobs', '?')} jobs"
            if st.button(label, key=f"load_{p.name}"):
                st.session_state.active_run_dir = p
                st.rerun()
