from datetime import datetime, timedelta, timezone

from kinsun.proactive.jobs import build_greeting_job, build_inactivity_job

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 6, 29, 10, 0, tzinfo=TPE)


def test_greeting_runs_for_each_session():
    greeted = []
    job = build_greeting_job(sessions=lambda: ["u1", "u2"], greet_one=greeted.append, hour=8)
    job.run()
    assert greeted == ["u1", "u2"]
    assert job.name == "daily-greeting"


def test_greeting_isolates_failure():
    greeted = []

    def greet_one(s):
        if s == "u1":
            raise RuntimeError("boom")
        greeted.append(s)

    build_greeting_job(sessions=lambda: ["u1", "u2"], greet_one=greet_one, hour=8).run()
    assert greeted == ["u2"]


def test_inactivity_only_cares_for_stale():
    cared = []
    last = {
        "u1": (NOW - timedelta(days=3)).timestamp(),  # 失聯
        "u2": (NOW - timedelta(hours=1)).timestamp(),  # 新近
        "u3": None,  # 從未發話 → 跳過
    }
    job = build_inactivity_job(
        sessions=lambda: ["u1", "u2", "u3"],
        last_active=lambda s: last[s],
        clock=lambda: NOW,
        threshold_seconds=2 * 86400,
        care_one=cared.append,
        hour=10,
    )
    job.run()
    assert cared == ["u1"]


def test_inactivity_isolates_failure():
    cared = []

    def care_one(s):
        if s == "u1":
            raise RuntimeError("boom")
        cared.append(s)

    old = (NOW - timedelta(days=5)).timestamp()
    build_inactivity_job(
        sessions=lambda: ["u1", "u2"],
        last_active=lambda s: old,
        clock=lambda: NOW,
        threshold_seconds=2 * 86400,
        care_one=care_one,
        hour=10,
    ).run()
    assert cared == ["u2"]
