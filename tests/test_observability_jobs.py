from kinsun.observability.jobs import build_observability_cleanup_job


def test_cleanup_job_cron_and_run():
    calls = []
    job = build_observability_cleanup_job(purge=lambda: calls.append(1), cron="45 3 * * *")
    assert job.name == "observability-cleanup"
    assert job.cron == "45 3 * * *"
    job.run()
    assert calls == [1]
