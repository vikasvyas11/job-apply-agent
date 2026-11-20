"""Shared fixtures: every test works against a throwaway content/ and output/
tree, so nothing here can read or overwrite the real CVs, settings or runs."""
import pytest

from job_apply_agent import config, local_settings, profiles, run_store

SAMPLE_CV = """# Jane Smith

{{LOCATION}} **|** jane@example.com | {{PHONE}} **|** [LinkedIn](https://linkedin.com/in/jane)

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

REGIONS = {
    "UK": {"location": "London", "phone": "+44-0000"},
    "India": {"location": "Bangalore", "phone": "99999"},
}


def _flow_files(flow: str) -> dict[str, str]:
    """Each flow gets its own marker text so tests can prove flows never mix."""
    marker = f"{flow.upper()}-ONLY"
    return {
        "resume.md": SAMPLE_CV.replace("Data scientist.", f"Data scientist. {marker} summary."),
        "coverletter_reference.md": f"Dear Hiring Manager,\n\n{marker} letter.\n\nBest,\nJane\n",
        "project_notes.md": f"Background detail. {marker} notes.",
        "prompts.md": SAMPLE_PROMPTS.replace("Write a letter.", f"Write a letter. {marker} prompt."),
    }


@pytest.fixture
def content(tmp_path, monkeypatch):
    """Point every content/settings/output path at tmp_path with sample data for all flows."""
    content_dir = tmp_path / "content"
    for flow in profiles.FLOWS:
        folder = content_dir / flow
        folder.mkdir(parents=True)
        for name, text in _flow_files(flow).items():
            (folder / name).write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_DIR", content_dir)

    monkeypatch.setattr(local_settings, "SETTINGS_FILE", tmp_path / "local_settings.json")
    local_settings.save({"applicant_name": "Jane Smith", "template_doc_id": "doc123", "regions": REGIONS})

    output = tmp_path / "output"
    monkeypatch.setattr(config, "OUTPUT_DIR", output)
    monkeypatch.setattr(run_store, "RUNS_DIR", output / "runs")
    monkeypatch.setattr(run_store, "CURRENT_RUN_MARKER", output / "current_run.txt")
    return tmp_path


@pytest.fixture
def profile(content):
    """The Data Science flow with the UK region."""
    return profiles.Profile(flow="data", region="UK")
