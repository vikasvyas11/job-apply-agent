import pytest

from job_apply_agent import company_research, docs_writer, jd_extractor, llm, pipeline
from job_apply_agent.pipeline import JobInput

PROFILE = None


@pytest.fixture(autouse=True)
def _profile(profile):
    """Every test here runs with the Data Science / UK profile from conftest."""
    global PROFILE
    PROFILE = profile

CV = "Jane\ncontact\n\nPROFESSIONAL SUMMARY\n" + "cv body " * 40
LETTER = "Dear Hiring Manager,\n" + "letter body " * 40


def stub_happy_path(monkeypatch):
    monkeypatch.setattr(
        jd_extractor, "get_jd",
        lambda text, pasted_fallback="": jd_extractor.JDResult(source="(pasted text)", text=text, ok=True),
    )
    monkeypatch.setattr(llm, "extract_job_meta", lambda jd, company_override="": {"company": "Acme", "job_title": "DS"})
    monkeypatch.setattr(company_research, "research_company", lambda c: company_research.ResearchResult(company=c))
    monkeypatch.setattr(llm, "generate_cv", lambda **k: CV)
    monkeypatch.setattr(llm, "generate_cover_letter", lambda **k: LETTER)
    monkeypatch.setattr(docs_writer, "get_clients", lambda **k: object())
    monkeypatch.setattr(docs_writer, "create_application_doc", lambda clients, **k: "https://docs.example/doc")


def test_happy_path_returns_doc_url(monkeypatch):
    stub_happy_path(monkeypatch)
    result = pipeline.run_job(JobInput(url_or_text="Some pasted job description"), profile=PROFILE)
    assert result.ok and result.doc_url == "https://docs.example/doc"
    assert result.company == "Acme" and result.job_title == "DS"
    assert "Tailored CV generated" in result.log


def test_unusable_jd_stops_before_any_generation(monkeypatch):
    monkeypatch.setattr(
        jd_extractor, "get_jd",
        lambda *a, **k: jd_extractor.JDResult(source="https://x", text="", ok=False, error="login wall"),
    )
    result = pipeline.run_job(JobInput(url_or_text="https://x"), profile=PROFILE)
    assert not result.ok and result.error == "login wall"


def test_ollama_failure_is_reported_not_raised(monkeypatch):
    stub_happy_path(monkeypatch)

    def fail(**k):
        raise llm.OllamaError("model down")

    monkeypatch.setattr(llm, "generate_cv", fail)
    result = pipeline.run_job(JobInput(url_or_text="jd"), profile=PROFILE)
    assert not result.ok and result.error == "model down"


def test_docs_failure_keeps_the_generated_text(monkeypatch):
    stub_happy_path(monkeypatch)

    def fail(clients, **k):
        raise RuntimeError("quota")

    monkeypatch.setattr(docs_writer, "create_application_doc", fail)
    result = pipeline.run_job(JobInput(url_or_text="jd"), profile=PROFILE)
    assert not result.ok
    assert "Google Docs write failed: quota" in result.error
    assert result.tailored_cv == CV and result.cover_letter == LETTER


def test_one_crashing_job_does_not_stop_the_batch(monkeypatch):
    stub_happy_path(monkeypatch)
    original = pipeline.run_job

    def flaky(job, *, profile, google_clients=None):
        if job.url_or_text == "bad":
            raise ValueError("unexpected")
        return original(job, profile=profile, google_clients=google_clients)

    monkeypatch.setattr(pipeline, "run_job", flaky)
    seen = []
    results = pipeline.run_batch(
        [JobInput("ok one"), JobInput("bad"), JobInput("ok two")], profile=PROFILE,
        on_result=lambda i, r: seen.append(i),
    )
    assert [r.ok for r in results] == [True, False, True]
    assert "Unexpected error: unexpected" in results[1].error
    assert seen == [0, 1, 2]


def test_batch_survives_google_auth_failure_up_front(monkeypatch):
    stub_happy_path(monkeypatch)

    def no_auth(**k):
        raise FileNotFoundError("credentials.json")

    monkeypatch.setattr(docs_writer, "get_clients", no_auth)
    results = pipeline.run_batch([JobInput("jd")], profile=PROFILE)
    assert not results[0].ok and "credentials.json" in results[0].error


def test_run_log_records_the_flow_and_region(monkeypatch):
    stub_happy_path(monkeypatch)
    result = pipeline.run_job(JobInput(url_or_text="jd"), profile=PROFILE)
    assert result.log[0] == "Flow: Data Science, region: UK"


def test_the_profile_reaches_both_generation_calls(monkeypatch):
    stub_happy_path(monkeypatch)
    seen = []
    monkeypatch.setattr(llm, "generate_cv", lambda **k: seen.append(("cv", k["profile"])) or CV)
    monkeypatch.setattr(llm, "generate_cover_letter", lambda **k: seen.append(("cl", k["profile"])) or LETTER)
    pipeline.run_job(JobInput(url_or_text="jd"), profile=PROFILE)
    assert seen == [("cv", PROFILE), ("cl", PROFILE)]


def test_background_runs_never_open_a_browser_for_google(monkeypatch):
    """An expired login during a batch must fail fast with a clear message, not
    open an OAuth window nobody is watching and hang the worker."""
    stub_happy_path(monkeypatch)
    calls = []

    def get_clients(**kwargs):
        calls.append(kwargs)
        raise docs_writer.GoogleLoginRequired("Your Google login has expired")

    monkeypatch.setattr(docs_writer, "get_clients", get_clients)
    results = pipeline.run_batch([JobInput("jd")], profile=PROFILE)
    assert calls and all(c == {"interactive": False} for c in calls)
    assert "Google login has expired" in results[0].error
