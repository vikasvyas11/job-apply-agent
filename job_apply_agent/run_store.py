"""Persists batch-run progress/results to disk, so a run survives a Streamlit
browser-session reset (tab sleep/discard, disconnect, reload). The actual
work happens in a background thread tied to the server process, not to any
one browser session, and every job's result is written to disk the moment
it completes. The UI just reads whatever's on disk on every render, so
reopening the page (even much later, even a different browser) shows
whatever progress has been made.
"""
import json
import time
import uuid
from pathlib import Path

from job_apply_agent import config

RUNS_DIR = config.OUTPUT_DIR / "runs"
CURRENT_RUN_MARKER = config.OUTPUT_DIR / "current_run.txt"


def new_run(n_jobs: int, *, flow: str = "", region: str = "") -> Path:
    """Start a run folder. flow and region record which profile the batch used,
    so past runs can be labelled (older runs have neither)."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    write_status(run_dir, {
        "n_jobs": n_jobs, "completed": 0, "started_at": time.time(), "done": False,
        "flow": flow, "region": region,
    })
    # Only the run id is stored (not an absolute path), so the project folder
    # can be moved or renamed without orphaning the "resume last run" marker.
    CURRENT_RUN_MARKER.write_text(run_id, encoding="utf-8")
    return run_dir


def write_status(run_dir: Path, status: dict) -> None:
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")


def read_status(run_dir: Path) -> dict:
    path = run_dir / "status.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}  # being written concurrently; caller just tries again next render


def save_job_result(run_dir: Path, idx: int, result: dict) -> None:
    (run_dir / f"job_{idx}.json").write_text(json.dumps(result), encoding="utf-8")


def load_job_results(run_dir: Path) -> dict[int, dict]:
    results = {}
    for path in sorted(run_dir.glob("job_*.json")):
        idx = int(path.stem.split("_")[1])
        try:
            results[idx] = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue  # being written concurrently
    return results


def mark_job_failed(run_dir: Path, idx: int, job_url: str, error: str) -> None:
    """Used if the worker thread itself crashes unexpectedly (a bug, not a
    normal pipeline error) so the UI still shows *something* for that job
    instead of it just hanging forever with no result file. Also counts the
    job as completed so the progress bar can reach 100%."""
    save_job_result(
        run_dir, idx,
        {
            "url_or_text": job_url, "ok": False, "company": "", "job_title": "",
            "doc_url": "", "error": f"Worker thread crashed: {error}", "jd_source": "",
            "tailored_cv": "", "cover_letter": "", "log": [],
        },
    )
    status = read_status(run_dir)
    status["completed"] = status.get("completed", 0) + 1
    write_status(run_dir, status)


def get_current_run() -> Path | None:
    """The most recently started run, if it still exists on disk.

    Older versions stored an absolute path in the marker; taking just the
    final path component keeps those markers working after a folder move."""
    if not CURRENT_RUN_MARKER.exists():
        return None
    value = CURRENT_RUN_MARKER.read_text(encoding="utf-8").strip()
    if not value:
        return None
    run_dir = RUNS_DIR / Path(value.replace("\\", "/")).name
    return run_dir if run_dir.is_dir() else None


def list_runs() -> list[Path]:
    if not RUNS_DIR.exists():
        return []
    return sorted((p for p in RUNS_DIR.iterdir() if p.is_dir()), reverse=True)
