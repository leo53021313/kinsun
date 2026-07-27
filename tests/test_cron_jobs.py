from kinsun.cron.jobs import build_audio_cleanup_job, build_consolidation_job


def test_runs_for_each_session():
    done = []
    # ✅ 庚-48（A-21）：整理提前到 00:05——凌晨盲窗（昨日對話短長期兩不著）縮到 5 分鐘。
    job = build_consolidation_job(
        sessions=lambda: ["u1", "u2"], run_one=done.append, cron="5 0 * * *"
    )
    job.run()
    assert done == ["u1", "u2"]
    assert job.name == "daily-consolidation"
    assert job.cron == "5 0 * * *"


def test_one_session_failure_does_not_block_others():
    done = []

    def run_one(line_user_id):
        if line_user_id == "u1":
            raise RuntimeError("boom")
        done.append(line_user_id)

    job = build_consolidation_job(sessions=lambda: ["u1", "u2"], run_one=run_one, cron="0 3 * * *")
    job.run()
    assert done == ["u2"]


def test_audio_cleanup_job_runs_cleanup():
    ran = []
    job = build_audio_cleanup_job(cleanup=lambda: ran.append(True), cron="30 4 * * *")
    assert job.name == "audio-cleanup"
    assert job.cron == "30 4 * * *"
    job.run()
    assert ran == [True]
