from kinsun.cron.fanout import fanout_job


def test_runs_action_for_each_item():
    done = []
    job = fanout_job(name="t", cron="0 8 * * *", population=lambda: ["a", "b"], action=done.append)
    job.run()
    assert done == ["a", "b"]
    assert job.name == "t"


def test_the_given_cron_is_used_verbatim():
    """時刻由 cron/registry.py 宣告，fanout 一律原樣帶過——它不再自己算時刻
    （2026-07-27）。自己算過一次就會有第二份真相，而後台讀的是 registry 那份。"""
    job = fanout_job(name="t", cron="0,30 * * * *", population=lambda: [], action=lambda x: None)
    assert job.cron == "0,30 * * * *"


def test_one_item_failure_isolated():
    done = []

    def action(item):
        if item == "a":
            raise RuntimeError("boom")
        done.append(item)

    fanout_job(name="t", cron="0 8 * * *", population=lambda: ["a", "b"], action=action).run()
    assert done == ["b"]


def test_action_can_skip_via_early_return():
    done = []

    def action(item):
        if item % 2 == 0:
            return
        done.append(item)

    fanout_job(name="t", cron="0 8 * * *", population=lambda: [1, 2, 3, 4], action=action).run()
    assert done == [1, 3]


def test_item_id_used_for_failure_log(caplog):
    import logging

    def action(_item):
        raise RuntimeError("boom")

    with caplog.at_level(logging.ERROR):
        fanout_job(
            name="med",
            cron="0 8 * * *",
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
        cron="0 8 * * *",
        population=lambda: ["a", "boom", "b"],
        action=action,
    ).run()
    assert done == ["a", "b"]
    # 三筆都各自更新過 trace metadata，且帶上 job 名稱。
    metas = [c["metadata"] for c in calls if "metadata" in c]
    assert {"job": "daily-greeting", "item": "a"} in metas
    assert all(m["job"] == "daily-greeting" for m in metas)
    assert len(metas) == 3


# ── 配額退避（2026-07-27）──
#
# 實測 logs/scheduler.log：15 筆 RESOURCE_EXHAUSTED 全出在 daily-consolidation，
# 路徑是 fanout → consolidation → mem0.add → Gemini embedder——**完全不經過 llm.py**，
# 所以改 LLMError 一筆都碰不到。Gemini 回傳體要求的 retryDelay 實測是 0～29 秒。
#
# ⚠️ 重試是 opt-in 而非預設：問候 job 重試會**重複發訊息給長輩**。只有本身冪等的
# job（整理有 memory_consolidations 逐日標記）才可以開。


def _quota_error() -> Exception:
    return RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded")


def test_quota_failure_is_retried_when_the_job_opts_in():
    attempts = []
    slept: list[float] = []

    def action(item):
        attempts.append(item)
        if len(attempts) < 3:
            raise _quota_error()

    job = fanout_job(
        name="j",
        cron="0 3 * * *",
        population=lambda: ["e1"],
        action=action,
        retry_quota_attempts=3,
        sleep=slept.append,
    )
    job.run()
    assert attempts == ["e1", "e1", "e1"]
    assert slept, "重試之間必須退避，不可連打"


def test_non_quota_failure_is_not_retried():
    """一般程式錯誤重試幾次都一樣，只是把夜間批次拖長。"""
    attempts = []

    def action(item):
        attempts.append(item)
        raise ValueError("欄位缺漏")

    fanout_job(
        name="j",
        cron="0 3 * * *",
        population=lambda: ["e1"],
        action=action,
        retry_quota_attempts=3,
        sleep=lambda _s: None,
    ).run()
    assert attempts == ["e1"]


def test_retry_is_off_by_default():
    """⚠️ 預設不重試：問候與提醒 job 重試會讓長輩收到重複訊息。"""
    attempts = []

    def action(item):
        attempts.append(item)
        raise _quota_error()

    fanout_job(name="j", cron="0 3 * * *", population=lambda: ["e1"], action=action).run()
    assert attempts == ["e1"]


def test_exhausted_retries_still_isolate_the_item():
    """重試用盡仍要逐筆隔離——一位長輩失敗不可讓後面的人全部沒收到。"""
    seen = []

    def action(item):
        seen.append(item)
        if item == "e1":
            raise _quota_error()

    fanout_job(
        name="j",
        cron="0 3 * * *",
        population=lambda: ["e1", "e2"],
        action=action,
        retry_quota_attempts=2,
        sleep=lambda _s: None,
    ).run()
    assert seen == ["e1", "e1", "e2"]
