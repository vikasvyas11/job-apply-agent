from job_apply_agent import cv_formatter
from job_apply_agent.cv_formatter import parse_cv

CV = """Jane Smith
London | jane@example.com | [LinkedIn](https://linkedin.com/in/jane)

PROFESSIONAL SUMMARY
Data scientist who ships.

WORK EXPERIENCE

**Analyst** | Acme, London | Jan 2024 - Present
* Did a thing.
* Did another.
Tools/Skills: Python, SQL
PROJECTS
**Cohort Builder v2** | Open-source project, github.com/x/y | Oct 2026
* Built it.
"""


def test_classifies_every_line_kind():
    specs = parse_cv(CV)
    assert specs[0].kind == "name" and specs[0].text == "Jane Smith"
    assert specs[1].kind == "contact"
    by_text = {s.text: s.kind for s in specs}
    assert by_text["PROFESSIONAL SUMMARY"] == "heading"
    assert by_text["WORK EXPERIENCE"] == "heading"
    assert by_text["PROJECTS"] == "heading"
    assert by_text["Did a thing."] == "bullet"
    assert by_text["Tools/Skills: Python, SQL"] == "normal"


def test_entry_bolds_only_the_title():
    entry = next(s for s in parse_cv(CV) if s.kind == "entry" and s.text.startswith("Analyst"))
    assert entry.text == "Analyst | Acme, London | Jan 2024 - Present"
    assert entry.text[: entry.bold_len] == "Analyst"


def test_project_entry_with_url_is_an_entry():
    entry = next(s for s in parse_cv(CV) if s.text.startswith("Cohort Builder v2"))
    assert entry.kind == "entry"
    assert entry.text[: entry.bold_len] == "Cohort Builder v2"


def test_unbolded_entry_line_is_still_detected():
    specs = parse_cv("Jane\ncontact\nWORK EXPERIENCE\nAnalyst | Acme, London | 2024\n")
    assert specs[-1].kind == "entry"
    assert specs[-1].text[: specs[-1].bold_len] == "Analyst"


def test_contact_links_become_ranges_over_the_label():
    contact = parse_cv(CV)[1]
    assert contact.text.endswith("LinkedIn")
    ((start, end, url),) = contact.links
    assert contact.text[start:end] == "LinkedIn"
    assert url == "https://linkedin.com/in/jane"


def test_markdown_escapes_are_removed():
    specs = parse_cv("Jane\ncontact\nWORK EXPERIENCE\n**Analyst** | Acme | Jan 2024 \\- Present\n")
    assert "\\" not in specs[-1].text


def test_blank_lines_before_headings_are_dropped():
    specs = parse_cv("Jane\ncontact\nSUMMARY\ntext\n\n\nWORK EXPERIENCE\n* b\n")
    heading_idx = next(i for i, s in enumerate(specs) if s.text == "WORK EXPERIENCE")
    assert specs[heading_idx - 1].kind != "blank"


def test_build_tab_content_ranges_stay_inside_the_inserted_text():
    specs = parse_cv(CV)
    text, requests = cv_formatter.build_tab_content("t.1", base_index=1, specs=specs)
    for req in requests:
        body = req.get("updateTextStyle") or req.get("updateParagraphStyle") or req["createParagraphBullets"]
        rng = body["range"]
        assert 1 <= rng["startIndex"] < rng["endIndex"] <= len(text) + 1
        assert rng["tabId"] == "t.1"


def test_bold_ranges_land_on_the_entry_titles():
    text, requests = cv_formatter.build_tab_content("t.1", 1, parse_cv(CV))
    bold_ranges = [
        r["updateTextStyle"]["range"]
        for r in requests
        if r.get("updateTextStyle", {}).get("textStyle") == {"bold": True}
    ]
    bolded = {text[r["startIndex"] - 1 : r["endIndex"] - 1] for r in bold_ranges}
    assert {"Analyst", "Cohort Builder v2"} <= bolded


def test_consecutive_bullets_share_one_bullet_request():
    specs = parse_cv("Jane\ncontact\nWORK EXPERIENCE\n* a\n* b\n* c\n")
    _, requests = cv_formatter.build_tab_content("t.1", 1, specs)
    assert sum("createParagraphBullets" in r for r in requests) == 1
