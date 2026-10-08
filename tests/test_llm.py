import pytest

from job_apply_agent import config, llm

LONG = "x" * 500


def test_context_size_scales_with_prompt_and_is_clamped():
    assert llm._context_size_for("short") == llm.MIN_NUM_CTX
    big = "word " * 100_000
    assert llm._context_size_for(big) == llm.MAX_NUM_CTX
    mid = "a" * (llm.CHARS_PER_TOKEN_ESTIMATE * 20_000)
    assert llm.MIN_NUM_CTX < llm._context_size_for(mid) < llm.MAX_NUM_CTX


def test_generate_retries_once_at_max_context_when_output_is_short(monkeypatch):
    calls = []

    def fake_call(prompt, *, model, num_ctx):
        calls.append(num_ctx)
        return {"response": "tiny" if len(calls) == 1 else LONG}

    monkeypatch.setattr(llm, "_call_ollama", fake_call)
    assert llm.generate("prompt") == LONG
    assert calls == [llm.MIN_NUM_CTX, llm.MAX_NUM_CTX]


def test_generate_raises_when_still_too_short(monkeypatch):
    monkeypatch.setattr(llm, "_call_ollama", lambda *a, **k: {"response": "tiny", "done_reason": "stop"})
    with pytest.raises(llm.OllamaError, match="too short"):
        llm.generate("prompt")


def test_extract_job_meta_parses_and_applies_override(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "COMPANY: Acme Ltd\nTITLE: Data Scientist")
    assert llm.extract_job_meta("jd") == {"company": "Acme Ltd", "job_title": "Data Scientist"}
    assert llm.extract_job_meta("jd", company_override="Other")["company"] == "Other"


def test_extract_job_meta_never_raises(monkeypatch):
    def boom(*a, **k):
        raise llm.OllamaError("down")

    monkeypatch.setattr(llm, "generate", boom)
    assert llm.extract_job_meta("jd") == {"company": "Unknown Company", "job_title": "Role"}


def test_extract_job_meta_treats_unknown_as_missing(monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "COMPANY: Unknown\nTITLE: unknown")
    assert llm.extract_job_meta("jd") == {"company": "Unknown Company", "job_title": "Role"}


def test_cv_section_headings_follow_the_master_cv_in_order(content):
    headings = llm.cv_section_headings(config.CV_DUMP_FILE.read_text(encoding="utf-8"))
    assert headings == ["PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION", "PROJECTS"]


def test_cv_section_headings_accept_plain_all_caps_lines():
    cv = "Jane Smith\ncontact line\n\nPROFESSIONAL SUMMARY\ntext\n\nTECHNICAL SKILLS\n* SQL\n"
    assert llm.cv_section_headings(cv) == ["PROFESSIONAL SUMMARY", "TECHNICAL SKILLS"]


def test_cv_section_headings_never_treat_an_all_caps_name_as_a_heading():
    assert llm.cv_section_headings("# JANE SMITH\ncontact\n## SKILLS\n") == ["SKILLS"]


def test_cv_prompt_uses_cv_headings_not_hardcoded_ones(content):
    prompt = llm.build_cv_prompt(company="Acme", jd_text="the jd", research_block="research")
    assert "PROFESSIONAL SUMMARY, WORK EXPERIENCE, EDUCATION, PROJECTS" in prompt
    assert "ADDITIONAL EXPERIENCE" not in prompt
    assert "Edit the CV provided below for Acme." in prompt  # [RESUME] / [COMPANY] placeholders filled in
    assert "[COMPANY]" not in prompt and "[RESUME]" not in prompt


def test_cv_prompt_example_contains_no_personal_details(content):
    prompt = llm.build_cv_prompt(company="Acme", jd_text="jd", research_block="r")
    assert "**Job Title** | Organisation, Location | Mon YYYY - Mon YYYY" in prompt
    assert "Data Science Intern" not in prompt


def test_cover_letter_prompt_signs_off_with_the_configured_first_name(content):
    prompt = llm.build_cover_letter_prompt(company="Acme", jd_text="jd", research_block="r", tailored_cv="cv")
    assert '"Jane" on its own line' in prompt


def test_real_contact_header_overwrites_whatever_the_model_wrote(content):
    generated = "Jane Smith\nMade-up Town | 999\n\nPROFESSIONAL SUMMARY\nSummary text.\n"
    fixed = llm._enforce_real_contact_header(generated)
    assert "Made-up Town" not in fixed
    assert "jane@example.com" in fixed
    assert fixed.endswith("PROFESSIONAL SUMMARY\nSummary text.\n")


def test_header_left_alone_when_split_point_missing(content):
    assert llm._enforce_real_contact_header("no headings here") == "no headings here"


def test_generate_cv_retries_when_a_cover_letter_bleeds_in(content, monkeypatch):
    outputs = iter(["CV text\nDear Hiring Manager, ...", "PROFESSIONAL SUMMARY\nclean cv"])
    monkeypatch.setattr(llm, "generate", lambda *a, **k: next(outputs))
    assert "clean cv" in llm.generate_cv(company="Acme", jd_text="jd", research_block="r")


def test_generate_cv_gives_up_after_repeated_contamination(content, monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "Dear Hiring Manager, hello")
    with pytest.raises(llm.OllamaError, match="bled in"):
        llm.generate_cv(company="Acme", jd_text="jd", research_block="r")


def test_cover_letter_retries_past_cliches_then_returns_the_clean_draft(content, monkeypatch):
    drafts = iter(["I am passionate about data.", "I like building data tools."])
    monkeypatch.setattr(llm, "generate", lambda *a, **k: next(drafts))
    letter = llm.generate_cover_letter(company="A", jd_text="jd", research_block="r", tailored_cv="cv")
    assert letter == "I like building data tools."


def test_cover_letter_keeps_a_cliche_draft_if_nothing_cleaner_arrives(content, monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "A proven track record of work.")
    letter = llm.generate_cover_letter(company="A", jd_text="jd", research_block="r", tailored_cv="cv")
    assert "proven track record" in letter


def test_cover_letter_rejects_cv_contamination(content, monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "PROFESSIONAL SUMMARY\nWORK EXPERIENCE\nstuff")
    with pytest.raises(llm.OllamaError):
        llm.generate_cover_letter(company="A", jd_text="jd", research_block="r", tailored_cv="cv")


def test_missing_content_file_has_actionable_error(content):
    config.CV_DUMP_FILE.unlink()
    with pytest.raises(FileNotFoundError, match="Setup page"):
        llm._read_cv_dump()
