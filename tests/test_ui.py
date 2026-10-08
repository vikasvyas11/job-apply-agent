from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from job_apply_agent import ui

ROOT = Path(__file__).resolve().parent.parent


def checks(**overrides):
    args = {
        "name": "Jane", "template_id": "doc123", "cv_text": "my real cv", "placeholder_cv_text": "placeholder",
        "credentials_exist": True, "token_exists": True, "ollama": "ready", "model": "m",
    }
    args.update(overrides)
    return {c.key: c for c in ui.readiness_checks(**args)}


def test_everything_ready():
    assert all(c.ok for c in checks().values())


def test_placeholder_cv_is_not_ready():
    assert not checks(cv_text="placeholder")["cv"].ok
    assert not checks(cv_text="  placeholder \n")["cv"].ok  # whitespace-only differences still count as unchanged
    assert not checks(cv_text="")["cv"].ok


@pytest.mark.parametrize(
    ("ollama", "ok", "detail"),
    [
        ("ready", True, "m is pulled"),
        ("no_model", False, "m is not pulled yet"),
        ("down", False, "Ollama is not running"),
    ],
)
def test_model_check_reports_ollama_state(ollama, ok, detail):
    check = checks(ollama=ollama)["model"]
    assert (check.ok, check.detail) == (ok, detail)


def test_missing_google_pieces_are_reported_separately():
    result = checks(credentials_exist=False, token_exists=False, template_id=" ", name="")
    assert [k for k, c in result.items() if not c.ok] == ["name", "client", "template", "login"]


def test_meter_clamps_and_pluralises():
    assert 'style="width:50%"' in ui.meter(1, 2, "running")
    assert 'style="width:0%"' in ui.meter(0, 0, "interrupted")
    assert 'style="width:100%"' in ui.meter(9, 3, "finished")
    assert "1 of 1 posting done" in ui.meter(1, 1, "finished")
    assert "2 of 3 postings done" in ui.meter(2, 3, "running")


def test_chip_escapes_text():
    assert "<script>" not in ui.chip("<script>alert(1)</script>", "ok")


def test_theme_file_exists_and_defines_the_tokens_the_pages_use():
    css = (ROOT / "job_apply_agent" / "theme.css").read_text(encoding="utf-8")
    for needle in ("--marker", ".meter-fill", '[class*="st-key-sheet_', ".chip-ok", ".qnum"):
        assert needle in css


@pytest.mark.parametrize("page", ["streamlit_app.py", "app_pages/applications.py", "app_pages/setup.py"])
def test_pages_render_without_errors(content, monkeypatch, page):
    monkeypatch.setattr(ui, "ollama_status", lambda model: "down")  # never touch the network in tests
    at = AppTest.from_file(str(ROOT / page), default_timeout=30).run()
    assert not at.exception, [e.value for e in at.exception]
