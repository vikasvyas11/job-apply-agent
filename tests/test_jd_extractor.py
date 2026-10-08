from job_apply_agent import jd_extractor


def test_is_url():
    assert jd_extractor.is_url("https://example.com/job")
    assert jd_extractor.is_url("  HTTP://example.com")
    assert not jd_extractor.is_url("We are hiring a data scientist")


def test_short_text_is_not_usable():
    assert not jd_extractor._is_usable("too short")


def test_junk_marker_rejects_short_page_but_not_long_one():
    junk = "Please enable JavaScript to continue. " * 8
    assert len(junk) > jd_extractor.MIN_JD_CHARS
    assert not jd_extractor._is_usable(junk)
    long_real_page = ("Responsibilities include building pipelines. " * 60) + " enable cookies"
    assert jd_extractor._is_usable(long_real_page)


def test_non_url_input_is_treated_as_pasted_text():
    result = jd_extractor.get_jd("  Senior analyst role, 5 years experience  ")
    assert result.ok and result.source == "(pasted text)"
    assert result.text == "Senior analyst role, 5 years experience"


def test_empty_pasted_text_is_not_ok():
    assert not jd_extractor.get_jd("   ").ok


def test_failed_fetch_uses_pasted_fallback(monkeypatch):
    failure = jd_extractor.JDResult(source="https://x", text="", ok=False, error="blocked")
    monkeypatch.setattr(jd_extractor, "fetch_jd", lambda url: failure)
    result = jd_extractor.get_jd("https://x", pasted_fallback="  pasted description  ")
    assert result.ok and result.text == "pasted description"


def test_failed_fetch_without_fallback_reports_error(monkeypatch):
    failure = jd_extractor.JDResult(source="https://x", text="", ok=False, error="blocked")
    monkeypatch.setattr(jd_extractor, "fetch_jd", lambda url: failure)
    result = jd_extractor.get_jd("https://x")
    assert not result.ok and result.error == "blocked"
