import pytest

from job_apply_agent import llm, profiles

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


def test_cv_section_headings_follow_the_master_cv_in_order(profile):
    headings = llm.cv_section_headings(profile.resume_file.read_text(encoding="utf-8"))
    assert headings == ["PROFESSIONAL SUMMARY", "WORK EXPERIENCE", "EDUCATION", "PROJECTS"]


def test_cv_section_headings_accept_plain_all_caps_lines():
    cv = "Jane Smith\ncontact line\n\nPROFESSIONAL SUMMARY\ntext\n\nTECHNICAL SKILLS\n* SQL\n"
    assert llm.cv_section_headings(cv) == ["PROFESSIONAL SUMMARY", "TECHNICAL SKILLS"]


def test_cv_section_headings_never_treat_an_all_caps_name_as_a_heading():
    assert llm.cv_section_headings("# JANE SMITH\ncontact\n## SKILLS\n") == ["SKILLS"]


def test_cv_prompt_uses_cv_headings_not_hardcoded_ones(profile):
    prompt = llm.build_cv_prompt(profile=profile, company="Acme", jd_text="the jd", research_block="research")
    assert "PROFESSIONAL SUMMARY, WORK EXPERIENCE, EDUCATION, PROJECTS" in prompt
    assert "ADDITIONAL EXPERIENCE" not in prompt
    assert "Edit the CV provided below for Acme." in prompt  # [RESUME] / [COMPANY] placeholders filled in
    assert "[COMPANY]" not in prompt and "[RESUME]" not in prompt


def test_cv_prompt_example_contains_no_personal_details(profile):
    prompt = llm.build_cv_prompt(profile=profile, company="Acme", jd_text="jd", research_block="r")
    assert "**Job Title** | Organisation, Location | Mon YYYY - Mon YYYY" in prompt
    assert "Data Science Intern" not in prompt


@pytest.mark.parametrize("flow", sorted(profiles.FLOWS))
def test_each_flow_reads_only_its_own_content(content, flow):
    """The core guarantee of the three flows: a run never sees another flow's CV,
    notes, letter or prompts."""
    p = profiles.Profile(flow=flow, region="UK")
    cv_prompt = llm.build_cv_prompt(profile=p, company="Acme", jd_text="jd", research_block="r")
    letter_prompt = llm.build_cover_letter_prompt(
        profile=p, company="Acme", jd_text="jd", research_block="r", tailored_cv="cv"
    )
    own = f"{flow.upper()}-ONLY"
    assert f"{own} summary" in cv_prompt and f"{own} notes" in cv_prompt
    assert f"{own} letter" in letter_prompt and f"{own} prompt" in letter_prompt
    for other in profiles.FLOWS:
        if other != flow:
            assert f"{other.upper()}-ONLY" not in cv_prompt
            assert f"{other.upper()}-ONLY" not in letter_prompt


@pytest.mark.parametrize(
    ("region", "location", "phone"), [("UK", "London", "+44-0000"), ("India", "Bangalore", "99999")]
)
def test_region_fills_the_cv_contact_line(content, region, location, phone):
    p = profiles.Profile(flow="software", region=region)
    prompt = llm.build_cv_prompt(profile=p, company="Acme", jd_text="jd", research_block="r")
    assert f"{location} **|** jane@example.com | {phone}" in prompt
    assert "{{LOCATION}}" not in prompt and "{{PHONE}}" not in prompt


def test_cover_letter_prompt_keeps_location_and_phone_out(profile):
    prompt = llm.build_cover_letter_prompt(
        profile=profile, company="Acme", jd_text="jd", research_block="r", tailored_cv="cv"
    )
    assert "do not put my address, city, location or phone number" in prompt


def test_cover_letter_prompt_signs_off_with_the_configured_first_name(profile):
    prompt = llm.build_cover_letter_prompt(
        profile=profile, company="Acme", jd_text="jd", research_block="r", tailored_cv="cv"
    )
    assert '"Jane" on its own line' in prompt


def test_real_contact_header_overwrites_whatever_the_model_wrote(profile):
    generated = "Jane Smith\nMade-up Town | 999\n\nPROFESSIONAL SUMMARY\nSummary text.\n"
    fixed = llm._enforce_real_contact_header(generated, profile)
    assert "Made-up Town" not in fixed
    assert "London | jane@example.com | +44-0000" in fixed
    assert fixed.endswith("PROFESSIONAL SUMMARY\nSummary text.\n")


def test_contact_header_follows_the_chosen_region(content):
    india = profiles.Profile(flow="data", region="India")
    fixed = llm._enforce_real_contact_header("Jane\nx\n\nPROFESSIONAL SUMMARY\ntext\n", india)
    assert "Bangalore | jane@example.com | 99999" in fixed
    assert "London" not in fixed


def test_header_left_alone_when_split_point_missing(profile):
    assert llm._enforce_real_contact_header("no headings here", profile) == "no headings here"


def test_generate_cv_retries_when_a_cover_letter_bleeds_in(profile, monkeypatch):
    outputs = iter(["CV text\nDear Hiring Manager, ...", "PROFESSIONAL SUMMARY\nclean cv"])
    monkeypatch.setattr(llm, "generate", lambda *a, **k: next(outputs))
    assert "clean cv" in llm.generate_cv(profile=profile, company="Acme", jd_text="jd", research_block="r")


def test_generate_cv_gives_up_after_repeated_contamination(profile, monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "Dear Hiring Manager, hello")
    with pytest.raises(llm.OllamaError, match="bled in"):
        llm.generate_cv(profile=profile, company="Acme", jd_text="jd", research_block="r")


def test_cover_letter_retries_past_cliches_then_returns_the_clean_draft(profile, monkeypatch):
    drafts = iter(["I am passionate about data.", "I like building data tools."])
    monkeypatch.setattr(llm, "generate", lambda *a, **k: next(drafts))
    letter = llm.generate_cover_letter(
        profile=profile, company="A", jd_text="jd", research_block="r", tailored_cv="cv"
    )
    assert letter == "I like building data tools."


def test_cover_letter_keeps_a_cliche_draft_if_nothing_cleaner_arrives(profile, monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "A proven track record of work.")
    letter = llm.generate_cover_letter(
        profile=profile, company="A", jd_text="jd", research_block="r", tailored_cv="cv"
    )
    assert "proven track record" in letter


def test_cover_letter_rejects_cv_contamination(profile, monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: "PROFESSIONAL SUMMARY\nWORK EXPERIENCE\nstuff")
    with pytest.raises(llm.OllamaError):
        llm.generate_cover_letter(profile=profile, company="A", jd_text="jd", research_block="r", tailored_cv="cv")


def test_missing_content_file_has_actionable_error(profile):
    profile.resume_file.unlink()
    with pytest.raises(FileNotFoundError, match="Setup page"):
        llm._read_cv_dump(profile)


MASTER = """# Jane Smith

London | jane@example.com

## **WORK EXPERIENCE**

**AI and Automation Consultant** | Acme Consulting, Leeds | Oct 2026 \\- Present

* Automated things.

**Data Science Intern |** Somewhere University, Town *|* Jun 2026 \\- Sep 2026

* Linked records.

## **EDUCATION**

**University College London,** United Kingdom | MSc. Data | 2024 \\- 2025

## **PROJECTS**

**Cohort Builder v2** | Open-source project | Oct 2026

* Built it.
"""


def test_invented_entries_are_dropped_with_their_bullets():
    # Seen in a real run: the model split one project into a made-up "V1" and
    # promoted background notes into an entry the master CV does not have.
    generated = (
        "Jane Smith\ncontact\n\nWORK EXPERIENCE\n"
        "AI AND AUTOMATION CONSULTANT | Acme Consulting, Leeds | Oct 2026 - Present\n* Automated things.\n"
        "PROJECTS\n"
        "COHORT BUILDER V2 | Open-source project | Oct 2026\n* Built it.\n"
        "COHORT BUILDER V1 | Personal project | Oct 2026\n* Invented bullet.\n* Another invented bullet.\n"
        "JOB APPLICATION AGENT | Personal project | N/A\n* Not in this CV.\n"
        "EDUCATION\n"
        "UNIVERSITY COLLEGE LONDON, United Kingdom | MSc Data | 2024 - 2025\n"
    )
    cleaned, removed = llm.drop_invented_entries(generated, MASTER)
    assert removed == ["COHORT BUILDER V1", "JOB APPLICATION AGENT"]
    assert "Invented bullet" not in cleaned and "Not in this CV" not in cleaned
    assert "EDUCATION" in cleaned  # the section after a dropped entry survives
    assert "Built it." in cleaned


def test_entry_titles_get_the_master_cvs_casing():
    generated = (
        "Jane\nc\nWORK EXPERIENCE\nDATA SCIENCE INTERN | Somewhere University, Town | 2026\n"
        "COHORT BUILDER V2 | Open-source project | Oct 2026\n"
        "UNIVERSITY COLLEGE LONDON, United Kingdom | MSc | 2025\n"
    )
    cleaned, removed = llm.drop_invented_entries(generated, MASTER)
    assert removed == []
    assert "Data Science Intern | Somewhere" in cleaned
    assert "Cohort Builder v2 |" in cleaned
    assert "University College London, United Kingdom |" in cleaned


def test_rephrased_title_at_a_known_organisation_is_kept():
    generated = "Jane\nc\nWORK EXPERIENCE\n**AI & Automation Consultant** | Acme Consulting, Leeds | 2026\n* x\n"
    cleaned, removed = llm.drop_invented_entries(generated, MASTER)
    assert removed == [] and "* x" in cleaned


def test_generate_cv_applies_the_entry_check(profile, monkeypatch):
    monkeypatch.setattr(llm, "generate", lambda *a, **k: (
        "Jane Smith\nx\n\nPROFESSIONAL SUMMARY\nSummary.\nWORK EXPERIENCE\n"
        "**Analyst** | Acme, London | 2024\n* Real.\n**Made Up Role** | Nowhere Ltd, Mars | 2030\n* Fake.\n"
    ))
    cv = llm.generate_cv(profile=profile, company="A", jd_text="jd", research_block="r")
    assert "Real." in cv and "Made Up Role" not in cv and "Fake." not in cv


def test_prompts_carry_the_accuracy_rules(profile):
    cv_prompt = llm.build_cv_prompt(profile=profile, company="A", jd_text="jd", research_block="r")
    letter_prompt = llm.build_cover_letter_prompt(
        profile=profile, company="A", jd_text="jd", research_block="r", tailored_cv="cv"
    )
    assert "never turn it into a new entry" in cv_prompt
    assert 'say supported, not led' in cv_prompt and 'say supported, not led' in letter_prompt


def test_entry_check_never_touches_the_header():
    generated = "JANE SMITH | me@example.com | 123\nother line\nPROFESSIONAL SUMMARY\ntext\n"
    cleaned, removed = llm.drop_invented_entries(generated, MASTER)
    assert removed == [] and cleaned.startswith("JANE SMITH | me@example.com")
