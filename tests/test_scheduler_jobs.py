from kinsun.scheduler.jobs import build_consolidation_job


def test_runs_for_each_session():
    done = []
    job = build_consolidation_job(sessions=lambda: ["u1", "u2"], run_one=done.append, hour=3)
    job.run()
    assert done == ["u1", "u2"]
    assert job.name == "daily-consolidation"
    assert job.cron == "0 3 * * *"


def test_one_session_failure_does_not_block_others():
    done = []

    def run_one(session_id):
        if session_id == "u1":
            raise RuntimeError("boom")
        done.append(session_id)

    job = build_consolidation_job(sessions=lambda: ["u1", "u2"], run_one=run_one, hour=3)
    job.run()
    assert done == ["u2"]
