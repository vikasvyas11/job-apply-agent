"""User-editable settings, persisted as JSON and set through the in-app Setup
page — nobody using this copy of the app should ever need to open a .py file.
config.py reads these at import time and falls back to sensible defaults if
the settings file doesn't exist yet (first run).
"""
import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "local_settings.json"

DEFAULTS = {
    "applicant_name": "",
    "template_doc_id": "",
    "ollama_model": "qwen3.5:latest",
    "output_folder_id": "",
}


def load() -> dict:
    if not SETTINGS_FILE.exists():
        return dict(DEFAULTS)
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(data)
    return merged


def save(updates: dict) -> None:
    current = load()
    current.update(updates)
    SETTINGS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")


def is_configured() -> bool:
    settings = load()
    return bool(settings["applicant_name"] and settings["template_doc_id"])
