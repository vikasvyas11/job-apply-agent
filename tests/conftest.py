"""Shared fixtures: every test works against a throwaway content/ and output/
tree, so nothing here can read or overwrite the real CV, settings or runs."""
import pytest

from job_apply_agent import config, local_settings, run_store

SAMPLE_CV = """# Jane Smith

London **|** jane@example.com | 07000 000000 **|** [LinkedIn](https://linkedin.com/in/jane)

## **PROFESSIONAL SUMMARY**

Data scientist.

## **WORK EXPERIENCE**

**Analyst** | Acme, London | Jan 2024 \\- Present

* Did a thing.

## **EDUCATION**

**University of Somewhere,** UK | MSc. Data | 2022 \\- 2023

## **PROJECTS**

**Widget** | Open source | Oct 2026

* Built it.
"""

SAMPLE_PROMPTS = """Prompt for Resume:
Edit [RESUME] for [COMPANY].

Prompt for Cover letter:
Write a letter.

Writing Style:
British English.
"""


@pytest.fixture
def content(tmp_path, monkeypatch):
    """Point every content/settings/output path at tmp_path with sample data."""
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    files = {
        "CV_DUMP_FILE": ("resume.md", SAMPLE_CV),
        "COVER_LETTER_REFERENCE_FILE": ("coverletter_reference.md", "Dear Hiring Manager,\n\nBest,\nJane\n"),
        "PROJECT_NOTES_FILE": ("project_notes.md", "Background detail."),
        "PROMPTS_FILE": ("prompts.md", SAMPLE_PROMPTS),
    }
    for attr, (name, text) in files.items():
        path = content_dir / name
        path.write_text(text, encoding="utf-8")
        monkeypatch.setattr(config, attr, path)

    monkeypatch.setattr(local_settings, "SETTINGS_FILE", tmp_path / "local_settings.json")
    local_settings.save({"applicant_name": "Jane Smith", "template_doc_id": "doc123"})

    output = tmp_path / "output"
    monkeypatch.setattr(config, "OUTPUT_DIR", output)
    monkeypatch.setattr(run_store, "RUNS_DIR", output / "runs")
    monkeypatch.setattr(run_store, "CURRENT_RUN_MARKER", output / "current_run.txt")
    return tmp_path
