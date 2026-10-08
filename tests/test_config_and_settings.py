import pytest

from job_apply_agent import config, local_settings


def test_defaults_when_no_settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(local_settings, "SETTINGS_FILE", tmp_path / "missing.json")
    assert local_settings.load() == local_settings.DEFAULTS
    assert not local_settings.is_configured()


def test_corrupt_settings_file_falls_back_to_defaults(tmp_path, monkeypatch):
    bad = tmp_path / "local_settings.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(local_settings, "SETTINGS_FILE", bad)
    assert local_settings.load() == local_settings.DEFAULTS


def test_save_merges_and_is_configured(content):
    local_settings.save({"ollama_model": "llama3"})
    loaded = local_settings.load()
    assert loaded["ollama_model"] == "llama3"
    assert loaded["applicant_name"] == "Jane Smith"  # untouched by the partial save
    assert local_settings.is_configured()


def test_settings_are_read_live_not_cached_at_import(content):
    assert config.TEMPLATE_DOC_ID == "doc123"
    local_settings.save({"template_doc_id": "doc456"})
    assert config.TEMPLATE_DOC_ID == "doc456"


def test_applicant_name_placeholder_when_unset(tmp_path, monkeypatch):
    monkeypatch.setattr(local_settings, "SETTINGS_FILE", tmp_path / "none.json")
    assert config.APPLICANT_NAME == "Your Name"


def test_unknown_config_attribute_raises():
    with pytest.raises(AttributeError):
        config.NOT_A_REAL_SETTING  # noqa: B018


def test_ensure_content_files_seeds_missing_but_never_overwrites(tmp_path, monkeypatch):
    template_dir = tmp_path / "content.example"
    template_dir.mkdir()
    (template_dir / "resume.md").write_text("template", encoding="utf-8")
    (template_dir / "prompts.md").write_text("template prompts", encoding="utf-8")
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    (content_dir / "resume.md").write_text("mine", encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_DIR", content_dir)
    monkeypatch.setattr(config, "CONTENT_TEMPLATE_DIR", template_dir)

    config.ensure_content_files()

    assert (content_dir / "resume.md").read_text(encoding="utf-8") == "mine"
    assert (content_dir / "prompts.md").read_text(encoding="utf-8") == "template prompts"
