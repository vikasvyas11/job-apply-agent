"""User-editable settings, persisted as JSON and set through the in-app Setup
page, so nobody using the app should need to open a .py file. config.py reads
these on every access and falls back to sensible defaults if the settings file
doesn't exist yet (first run).
"""
import json
from copy import deepcopy
from pathlib import Path

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "local_settings.json"

DEFAULTS = {
    "applicant_name": "",
    "template_doc_id": "",
    "ollama_model": "qwen3.5:latest",
    "output_folder_id": "",
    # Contact details per region, used for the CV's {{LOCATION}} and {{PHONE}}
    # placeholders. Edit on the Setup page; add more regions here if you need them.
    "regions": {
        "UK": {"location": "London", "phone": ""},
        "India": {"location": "Bangalore", "phone": ""},
    },
}


def load() -> dict:
    merged = deepcopy(DEFAULTS)
    if not SETTINGS_FILE.exists():
        return merged
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return merged
    if isinstance(data, dict):
        merged.update(data)
    if not isinstance(merged.get("regions"), dict) or not merged["regions"]:
        merged["regions"] = deepcopy(DEFAULTS["regions"])
    return merged


def save(updates: dict) -> None:
    current = load()
    current.update(updates)
    SETTINGS_FILE.write_text(json.dumps(current, indent=2), encoding="utf-8")


def is_configured() -> bool:
    settings = load()
    return bool(settings["applicant_name"] and settings["template_doc_id"])
