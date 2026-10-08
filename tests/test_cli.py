import pytest

from job_apply_agent import cli
from job_apply_agent.pipeline import JobResult


def test_companies_are_matched_to_urls_by_position(monkeypatch):
    seen = []

    def fake_run_batch(jobs):
        seen.extend((j.url_or_text, j.company_name) for j in jobs)
        return [JobResult(job=j, ok=True, doc_url="https://doc") for j in jobs]

    monkeypatch.setattr(cli, "run_batch", fake_run_batch)
    code = cli.main(["--job-url", "https://a", "--job-url", "https://b", "--company", "Acme"])
    assert code == 0
    assert seen == [("https://a", "Acme"), ("https://b", "")]


def test_exit_code_is_nonzero_when_any_job_fails(monkeypatch):
    monkeypatch.setattr(cli, "run_batch", lambda jobs: [JobResult(job=jobs[0], ok=False, error="x")])
    assert cli.main(["--job-url", "https://a"]) == 1


def test_more_companies_than_urls_is_a_usage_error():
    with pytest.raises(SystemExit):
        cli.main(["--job-url", "https://a", "--company", "A", "--company", "B"])
