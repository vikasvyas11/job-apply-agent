"""Central configuration for the job-application agent.

Two kinds of settings live here:
  1. Fixed internals (file paths, API scopes), plain constants below.
  2. User-editable settings (your name, template doc ID, model, output
     folder), loaded from local_settings.json, which the in-app Setup page
     writes. Nobody should need to edit this file directly; use the Setup
     page instead.
"""
import shutil
from pathlib import Path

from job_apply_agent import local_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- Ollama (local LLM) ---
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_TIMEOUT_SECONDS = 600  # local generation on CPU/small GPU can be slow

# --- Source-of-truth content files (edit via the Setup page, or these files
# directly if you prefer a text editor; nothing is hardcoded elsewhere) ---
# One folder per flow: content/<flow>/{resume,project_notes,coverletter_reference,prompts}.md
# (see profiles.py). content.example/ has the same layout with placeholder text.
CONTENT_DIR = PROJECT_ROOT / "content"
CONTENT_TEMPLATE_DIR = PROJECT_ROOT / "content.example"

# --- Google APIs ---
GOOGLE_CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"  # OAuth client secret
GOOGLE_TOKEN_FILE = PROJECT_ROOT / "token.json"              # auto-created after first login
# drive.file (not drive) would only let the app see files it created itself:
# the hand-made template doc lives outside that, so files.copy on it 404s.
# Full "drive" scope is needed to read/copy a doc you created outside the app.
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

TAB_NAME_CV = "CV"
TAB_NAME_COVER_LETTER = "Cover Letter"

# --- Output/local logging ---
OUTPUT_DIR = PROJECT_ROOT / "output"


# User-editable settings, exposed as module attributes (config.OLLAMA_MODEL etc.)
# but read from local_settings.json on every access rather than once at import.
# The Setup page saves while the Streamlit server is running, and a value cached
# at import time would silently ignore those edits until a restart.
#   OLLAMA_MODEL      model name for Ollama
#   APPLICANT_NAME    your full name (falls back to a placeholder)
#   TEMPLATE_DOC_ID   ID of the hand-made Google Doc with "CV" and "Cover Letter" tabs
#   OUTPUT_FOLDER_ID  optional Drive folder for generated docs ("" = My Drive)
_SETTING_ATTRS = {
    "OLLAMA_MODEL": "ollama_model",
    "APPLICANT_NAME": "applicant_name",
    "TEMPLATE_DOC_ID": "template_doc_id",
    "OUTPUT_FOLDER_ID": "output_folder_id",
}


def __getattr__(name: str) -> str:
    key = _SETTING_ATTRS.get(name)
    if key is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = local_settings.load()[key]
    if name == "APPLICANT_NAME":
        return value or "Your Name"
    return value


def ensure_content_files() -> None:
    """Seed any missing content file from content.example/ (every flow folder)
    so a fresh checkout has something to edit on the Setup page instead of
    crashing on a missing file. Existing files are never overwritten."""
    for template in CONTENT_TEMPLATE_DIR.rglob("*.md"):
        target = CONTENT_DIR / template.relative_to(CONTENT_TEMPLATE_DIR)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(template, target)
