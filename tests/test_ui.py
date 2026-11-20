from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from job_apply_agent import ui

ROOT = Path(__file__).resolve().parent.parent


def checks(**overrides):
    args = {
        "name": "Jane", "template_id": "doc123", "cv_flows_ready": ["data", "growth", "software"],
        "total_flows": 3, "regions_ready": True,
        "credentials_exist": True, "google_login": "connected", "ollama": "ready", "model": "m",
    }
    args.update(overrides)
    return {c.key: c for c in ui.readiness_checks(**args)}


def test_everything_ready():
    assert all(c.ok for c in checks().values())


def test_cv_check_counts_ready_flows():
    assert checks(cv_flows_ready=["data"])["cv"].ok
    assert checks(cv_flows_ready=["data"])["cv"].detail == "1 of 3 flows ready"
    assert not checks(cv_flows_ready=[])["cv"].ok
    assert checks(cv_flows_ready=[])["cv"].detail == "Still the placeholder"


def test_regions_check():
    assert checks()["regions"].ok
    assert not checks(regions_ready=False)["regions"].ok


def test_flows_with_real_cv_ignores_placeholders(content, monkeypatch):
    from job_apply_agent import config

    template = content / "content.example"
    for flow in ("data", "growth", "software"):
        (template / flow).mkdir(parents=True)
        (template / flow / "resume.md").write_text("placeholder", encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_TEMPLATE_DIR", template)
    (content / "content" / "growth" / "resume.md").write_text("placeholder", encoding="utf-8")
    assert ui.flows_with_real_cv() == ["data", "software"]


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
    result = checks(credentials_exist=False, google_login="missing", template_id=" ", name="")
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
    monkeypatch.setattr(ui, "google_login_status", lambda: "missing")
    at = AppTest.from_file(str(ROOT / page), default_timeout=30).run()
    assert not at.exception, [e.value for e in at.exception]


def test_expired_google_login_is_not_reported_as_connected():
    login = checks(google_login="expired")["login"]
    assert not login.ok and "reconnect" in login.detail.lower()
