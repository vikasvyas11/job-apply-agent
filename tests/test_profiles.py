import pytest

from job_apply_agent import config, local_settings, profiles


def test_three_flows_with_readable_labels():
    assert profiles.FLOWS == {"data": "Data Science", "growth": "Growth", "software": "Software Dev"}


def test_each_flow_has_its_own_folder(content):
    paths = {profiles.Profile(flow=f, region="UK").resume_file for f in profiles.FLOWS}
    assert len(paths) == 3
    assert profiles.Profile(flow="growth", region="UK").prompts_file == content / "content" / "growth" / "prompts.md"


def test_render_fills_location_and_phone(content):
    line = "{{LOCATION}} | me@example.com | {{PHONE}} | [LinkedIn](https://x)"
    assert profiles.Profile(flow="data", region="UK").render(line) == "London | me@example.com | +44-0000 | [LinkedIn](https://x)"
    assert profiles.Profile(flow="data", region="India").render(line) == "Bangalore | me@example.com | 99999 | [LinkedIn](https://x)"


def test_render_drops_an_unset_value_and_its_separator(content):
    local_settings.save({"regions": {"UK": {"location": "London", "phone": ""}}})
    line = "{{LOCATION}} | me@example.com | {{PHONE}} | [LinkedIn](https://x)"
    assert profiles.Profile(flow="data", region="UK").render(line) == "London | me@example.com | [LinkedIn](https://x)"


def test_unknown_flow_or_region_is_rejected(content):
    with pytest.raises(ValueError, match="flow"):
        profiles.Profile(flow="marketing", region="UK")
    with pytest.raises(ValueError, match="region"):
        profiles.Profile(flow="data", region="Mars")


def test_regions_default_when_settings_have_none(tmp_path, monkeypatch):
    monkeypatch.setattr(local_settings, "SETTINGS_FILE", tmp_path / "missing.json")
    assert list(profiles.regions()) == ["UK", "India"]
    assert profiles.default_region() == "UK"


def test_empty_regions_in_settings_fall_back_to_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(local_settings, "SETTINGS_FILE", tmp_path / "s.json")
    local_settings.save({"regions": {}})
    assert list(profiles.regions()) == ["UK", "India"]


def test_ensure_content_files_seeds_every_flow_folder(tmp_path, monkeypatch):
    template = tmp_path / "content.example"
    for flow in profiles.FLOWS:
        (template / flow).mkdir(parents=True)
        for name in profiles.CONTENT_FILES:
            (template / flow / name).write_text(f"{flow} {name}", encoding="utf-8")
    content_dir = tmp_path / "content"
    (content_dir / "growth").mkdir(parents=True)
    (content_dir / "growth" / "resume.md").write_text("my real growth cv", encoding="utf-8")
    monkeypatch.setattr(config, "CONTENT_DIR", content_dir)
    monkeypatch.setattr(config, "CONTENT_TEMPLATE_DIR", template)

    config.ensure_content_files()

    for flow in profiles.FLOWS:
        for name in profiles.CONTENT_FILES:
            assert (content_dir / flow / name).exists()
    assert (content_dir / "growth" / "resume.md").read_text(encoding="utf-8") == "my real growth cv"
