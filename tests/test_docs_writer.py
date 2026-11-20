import pytest
from googleapiclient.errors import HttpError

from job_apply_agent import docs_writer


class FakeResp:
    def __init__(self, status):
        self.status = status
        self.reason = "x"


class FlakyRequest:
    """Stands in for a googleapiclient request: fails with the given errors, then succeeds."""

    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = 0

    def execute(self):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return {"ok": True}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(docs_writer.time, "sleep", lambda s: None)


def test_clean_for_docs_strips_markdown():
    raw = "# Heading\n**bold** text\n* a bullet\n- another\n---\n__under__"
    assert docs_writer._clean_for_docs(raw) == "Heading\nbold text\n• a bullet\n• another\nunder\n"


def test_tab_ids_by_title_and_end_index():
    doc = {
        "tabs": [
            {"tabProperties": {"title": "CV", "tabId": "t.0"},
             "documentTab": {"body": {"content": [{"endIndex": 5}, {"endIndex": 42}]}}},
            {"tabProperties": {"title": "Cover Letter", "tabId": "t.1"}, "documentTab": {"body": {"content": []}}},
        ]
    }
    assert docs_writer.tab_ids_by_title(doc) == {"CV": "t.0", "Cover Letter": "t.1"}
    assert docs_writer._tab_end_index(doc, "t.0") == 42
    assert docs_writer._tab_end_index(doc, "t.1") == 1
    assert docs_writer._tab_end_index(doc, "missing") == 1


def test_doc_name_uses_configured_applicant_and_sanitises_slashes(content):
    assert docs_writer._doc_name("A/B Ltd", "Data\\Scientist") == "A-B Ltd - Data-Scientist - Jane Smith"
    assert docs_writer._doc_name("", "") == "Unknown Company - Role - Jane Smith"


def test_retry_recovers_from_transient_server_error():
    request = FlakyRequest([HttpError(FakeResp(503), b"unavailable")])
    assert docs_writer._execute_with_retry(request) == {"ok": True}
    assert request.calls == 2


def test_retry_recovers_from_dropped_connection():
    request = FlakyRequest([ConnectionError("reset")])
    assert docs_writer._execute_with_retry(request) == {"ok": True}


def test_client_errors_are_not_retried():
    request = FlakyRequest([HttpError(FakeResp(404), b"not found")])
    with pytest.raises(HttpError):
        docs_writer._execute_with_retry(request)
    assert request.calls == 1


def test_gives_up_after_the_configured_attempts():
    request = FlakyRequest([HttpError(FakeResp(500), b"boom")] * 5)
    with pytest.raises(HttpError):
        docs_writer._execute_with_retry(request, attempts=3)
    assert request.calls == 3


def test_refuses_to_write_near_empty_generation(content):
    with pytest.raises(ValueError, match="looks empty"):
        docs_writer.create_application_doc(
            clients=None, company="A", job_title="B", cv_text="tiny", cover_letter_text="x" * 300
        )


def test_refuses_without_a_template_id(content):
    from job_apply_agent import local_settings

    local_settings.save({"template_doc_id": ""})
    with pytest.raises(ValueError, match="TEMPLATE_DOC_ID"):
        docs_writer.create_application_doc(
            clients=None, company="A", job_title="B", cv_text="x" * 300, cover_letter_text="x" * 300
        )


def test_cover_letter_gets_one_explicit_style_over_the_whole_text():
    letter = "Dear Hiring Manager,\n\nBody.\n\nBest,\nJane\n"
    paragraph, text = docs_writer.cover_letter_style_requests("t.2", letter)
    rng = paragraph["updateParagraphStyle"]["range"]
    assert (rng["startIndex"], rng["endIndex"], rng["tabId"]) == (1, 1 + len(letter), "t.2")
    style = paragraph["updateParagraphStyle"]["paragraphStyle"]
    assert style["lineSpacing"] == docs_writer.COVER_LETTER_LINE_SPACING_PCT
    assert text["updateTextStyle"]["textStyle"]["fontSize"]["magnitude"] == docs_writer.COVER_LETTER_FONT_PT
    assert text["updateTextStyle"]["range"]["endIndex"] <= 1 + len(letter)


def test_login_status_missing_without_a_token(tmp_path, monkeypatch):
    monkeypatch.setattr(docs_writer.config, "GOOGLE_TOKEN_FILE", tmp_path / "token.json")
    assert docs_writer.login_status() == "missing"


def test_non_interactive_clients_raise_instead_of_opening_a_browser(tmp_path, monkeypatch):
    monkeypatch.setattr(docs_writer.config, "GOOGLE_TOKEN_FILE", tmp_path / "token.json")

    def no_browser(*a, **k):
        raise AssertionError("must not start an OAuth browser flow")

    monkeypatch.setattr(docs_writer.InstalledAppFlow, "from_client_secrets_file", no_browser)
    with pytest.raises(docs_writer.GoogleLoginRequired, match="Connect Google account"):
        docs_writer.get_clients(interactive=False)
