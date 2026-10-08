from job_apply_agent import run_store


def test_new_run_creates_status_and_marker(content):
    run_dir = run_store.new_run(3)
    assert run_store.read_status(run_dir)["n_jobs"] == 3
    assert run_store.get_current_run() == run_dir
    # the marker holds only the run id, so moving the project folder can't break it
    assert run_store.CURRENT_RUN_MARKER.read_text(encoding="utf-8") == run_dir.name


def test_marker_with_legacy_absolute_path_still_resolves(content):
    run_dir = run_store.new_run(1)
    run_store.CURRENT_RUN_MARKER.write_text(f"C:\\old\\location\\output\\runs\\{run_dir.name}", encoding="utf-8")
    assert run_store.get_current_run() == run_dir


def test_marker_pointing_at_missing_run_is_ignored(content):
    run_store.new_run(1)
    run_store.CURRENT_RUN_MARKER.write_text("does-not-exist", encoding="utf-8")
    assert run_store.get_current_run() is None


def test_job_results_round_trip_and_skip_corrupt_files(content):
    run_dir = run_store.new_run(2)
    run_store.save_job_result(run_dir, 0, {"ok": True})
    (run_dir / "job_1.json").write_text("{partial", encoding="utf-8")  # mid-write
    assert run_store.load_job_results(run_dir) == {0: {"ok": True}}


def test_mark_job_failed_counts_as_completed(content):
    run_dir = run_store.new_run(1)
    run_store.mark_job_failed(run_dir, 0, "https://x", "boom")
    assert run_store.load_job_results(run_dir)[0]["error"] == "Worker thread crashed: boom"
    assert run_store.read_status(run_dir)["completed"] == 1


def test_list_runs_newest_first(content):
    first = run_store.new_run(1)
    (first.parent / "20990101-000000-aaaaaa").mkdir()
    assert run_store.list_runs()[0].name == "20990101-000000-aaaaaa"
