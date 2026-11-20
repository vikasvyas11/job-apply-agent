import pytest

from job_apply_agent import prompt_loader


def test_splits_the_three_sections(profile):
    prompts = prompt_loader.load_prompts(profile.prompts_file)
    assert prompts.resume == "Edit [RESUME] for [COMPANY]."
    assert prompts.cover_letter == "Write a letter. DATA-ONLY prompt."
    assert prompts.writing_style == "British English."


def test_sections_may_appear_in_any_order(profile):
    profile.prompts_file.write_text(
        "Writing Style:\nstyle\n\nPrompt for Cover letter:\nletter\n\nPrompt for Resume:\ncv\n", encoding="utf-8"
    )
    prompts = prompt_loader.load_prompts(profile.prompts_file)
    assert (prompts.resume, prompts.cover_letter, prompts.writing_style) == ("cv", "letter", "style")


def test_missing_heading_raises_clear_error(profile):
    profile.prompts_file.write_text("Prompt for Resume:\ncv\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing the expected heading"):
        prompt_loader.load_prompts(profile.prompts_file)
