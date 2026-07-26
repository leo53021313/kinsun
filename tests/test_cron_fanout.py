import pytest

from kinsun.cron.fanout import fanout_job


def test_runs_action_for_each_item_and_builds_cron():
    done = []
    job = fanout_job(name="t", hour=8, population=lambda: ["a", "b"], action=done.append)
    job.run()
    assert done == ["a", "b"]
    assert job.name == "t"
    assert job.cron == "0 8 * * *"


def test_minute_in_cron():
    job = fanout_job(name="t", hour=3, minute=30, population=lambda: [], action=lambda x: None)
    assert job.cron == "30 3 * * *"


def test_an_explicit_cron_is_used_verbatim():
    """問候 job 要每半小時掃一次（spec 2026-07-16），hour／minute 組不出這種 cron。"""
    job = fanout_job(name="t", cron="0,30 * * * *", population=lambda: [], action=lambda x: None)
    assert job.cron == "0,30 * * * *"


def test_giving_both_hour_and_cron_fails_fast():
    """兩個都給時哪個生效無從得知，靜默採用其一等於讓 job 在不明時刻跑。"""
    with pytest.raises(ValueError):
        fanout_job(
            name="t", hour=8, cron="0,30 * * * *", population=lambda: [], action=lambda x: None
        )


def test_giving_neither_hour_nor_cron_fails_fast():
    with pytest.raises(ValueError):
        fanout_job(name="t", population=lambda: [], action=lambda x: None)


def test_one_item_failure_isolated():
    done = []

    def action(item):
        if item == "a":
            raise RuntimeError("boom")
        done.append(item)

    fanout_job(name="t", hour=8, population=lambda: ["a", "b"], action=action).run()
    assert done == ["b"]


def test_action_can_skip_via_early_return():
    done = []

    def action(item):
        if item % 2 == 0:
            return
        done.append(item)

    fanout_job(name="t", hour=8, population=lambda: [1, 2, 3, 4], action=action).run()
    assert done == [1, 3]


def test_item_id_used_for_failure_log(caplog):
    import logging

    def action(_item):
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        fanout_job(
            name="med",
            hour=8,
            population=lambda: [("e1", ["藥"])],
            action=action,
            item_id=lambda it: it[0],
        ).run()
    assert "e1" in caplog.text


def _enable_hermetic_tracing(monkeypatch) -> list[dict]:
    """把工程觀測切成啟用、但完全 hermetic（不連 Opik）：假的 track＝identity、
    update_current_trace 改為記錄呼叫。回傳的 list 收集每次 trace metadata 更新，
    用來斷言啟用路徑確實被走到（否則測試會空過）。"""
    import opik

    from kinsun.tracing import client as tracing_client

    calls: list[dict] = []
    monkeypatch.setattr(tracing_client, "_ENABLED", True)
    monkeypatch.setattr(opik, "track", lambda **kw: lambda f: f)
    monkeypatch.setattr(opik.opik_context, "update_current_trace", lambda **kw: calls.append(kw))
    return calls


def test_transparent_when_tracing_enabled(monkeypatch):
    """啟用 Opik 時，每筆包一層 root @track 仍須逐筆照跑、單筆失敗照隔離，
    且該筆的 job／item metadata 確實掛上 trace（證明走的是啟用路徑）。"""
    calls = _enable_hermetic_tracing(monkeypatch)
    done = []

    def action(item):
        if item == "boom":
            raise RuntimeError("x")
        done.append(item)

    fanout_job(
        name="daily-greeting",
        hour=8,
        population=lambda: ["a", "boom", "b"],
        action=action,
    ).run()
    assert done == ["a", "b"]
    # 三筆都各自更新過 trace metadata，且帶上 job 名稱。
    metas = [c["metadata"] for c in calls if "metadata" in c]
    assert {"job": "daily-greeting", "item": "a"} in metas
    assert all(m["job"] == "daily-greeting" for m in metas)
    assert len(metas) == 3
