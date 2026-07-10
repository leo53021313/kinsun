"""worker 組裝根：build_scheduler 的全 job 接線與閉包行為（M-8 覆蓋補強）。

外部相依與共用物件圖（assemble_core）以假 Core 替換，build_scheduler 自己的
接線邏輯照常執行——驗證「哪些 job 有掛、哪些條件不掛、job 跑起來接對線」。
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import kinsun.scheduler.worker as worker
from kinsun.accounts.models import PrincipalType
from kinsun.config import load_settings

_BASE_ENV = {
    "LINE_CHANNEL_SECRET": "test-secret",
    "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
    "GEMINI_API_KEY": "test-key",
    "DATABASE_URL": "postgresql://unused/unused",
}

_BASE_JOB_NAMES = [
    "daily-consolidation",
    "daily-greeting",
    "inactivity-care",
    "medication-morning",
    "medication-noon",
    "medication-evening",
    "medication-bedtime",
    "appointment-reminder",
    "observability-cleanup",
]


class _FakeDb:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakeLLM:
    def generate(self, *, system_prompt, messages):
        return "好"

    def generate_tool_turn(self, **kwargs):
        raise NotImplementedError


class _SpyRouter:
    def __init__(self, *, reachable: bool = True) -> None:
        self.reachable = reachable
        self.sent: list[tuple[PrincipalType, str, str]] = []

    def has_route(self, principal_type, principal_id) -> bool:
        return self.reachable

    def send_text(self, principal_type, principal_id, text) -> int:
        self.sent.append((principal_type, principal_id, text))
        return 1


class _SpyReminderLogs:
    def __init__(self) -> None:
        self.recorded: list[tuple[str, str, str]] = []

    def record(self, elder_id: str, kind: str, content: str) -> None:
        self.recorded.append((elder_id, kind, content))


def _fake_core(
    settings,
    *,
    elders: list[str] | None = None,
    router: _SpyRouter | None = None,
    reminder_logs: _SpyReminderLogs | None = None,
    last_active=None,
):
    elders = elders if elders is not None else []
    return SimpleNamespace(
        settings=settings,
        db=_FakeDb(),
        gemini=_FakeLLM(),
        long_term=object(),
        messenger=object(),
        router=router or _SpyRouter(),
        accounts=SimpleNamespace(
            get_elder=lambda elder_id: None,
            guardians_of=lambda elder_id: [],
        ),
        med_store=SimpleNamespace(list_for_slot=lambda slot: []),
        appt_store=SimpleNamespace(list_for_date=lambda date_str: []),
        medications=object(),
        appointments=object(),
        memory=SimpleNamespace(
            sessions=lambda: list(elders),
            last_active=last_active or (lambda elder_id: None),
        ),
        traces=SimpleNamespace(purge_older_than=lambda cutoff: None),
        reminder_logs=reminder_logs or _SpyReminderLogs(),
        notifications=object(),
        agent=SimpleNamespace(proactive=lambda elder_id, intent: f"主動：{intent}"),
    )


def _settings(**overrides):
    return load_settings({**_BASE_ENV, **overrides})


def _clock() -> datetime:
    return datetime(2026, 7, 10, 9, 0, tzinfo=ZoneInfo("Asia/Taipei"))


def _build(monkeypatch, settings, **core_kwargs):
    core = _fake_core(settings, **core_kwargs)
    monkeypatch.setattr(worker, "build_externals", lambda s: object())
    monkeypatch.setattr(worker, "assemble_core", lambda s, externals, *, clock: core)
    scheduler, db = worker.build_scheduler(settings, clock=_clock)
    return scheduler, core


def _job(scheduler, name: str):
    return next(j for j in scheduler._jobs if j.name == name)


def test_build_scheduler_wires_base_jobs(monkeypatch):
    scheduler, _core = _build(monkeypatch, _settings())
    assert [j.name for j in scheduler._jobs] == _BASE_JOB_NAMES


def test_dgx_with_storage_adds_audio_cleanup_jobs(monkeypatch):
    settings = _settings(
        TTS_BACKEND="dgx",
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_KEY="service-key",
    )
    scheduler, _core = _build(monkeypatch, settings)
    names = [j.name for j in scheduler._jobs]
    assert "audio-cleanup" in names
    assert "inbound-audio-cleanup" in names


def test_retention_zero_disables_audio_cleanup(monkeypatch):
    """AUDIO_RETENTION_DAYS=0＝音檔本體不刪（2026-07-09 修訂）：兩個清理 job 都不掛。"""
    settings = _settings(
        TTS_BACKEND="dgx",
        SUPABASE_URL="https://demo.supabase.co",
        SUPABASE_SERVICE_KEY="service-key",
        AUDIO_RETENTION_DAYS="0",
    )
    scheduler, _core = _build(monkeypatch, settings)
    names = [j.name for j in scheduler._jobs]
    assert "audio-cleanup" not in names
    assert "inbound-audio-cleanup" not in names


def test_summary_model_override_builds_dedicated_client(monkeypatch):
    """✅ D-16（丁-5）：GEMINI_MODEL_SUMMARY 與主模型不同時，摘要用專屬 client。"""
    built_models: list[str] = []

    def _spy_build(settings, model):
        built_models.append(model)
        return _FakeLLM()

    monkeypatch.setattr(worker, "build_gemini_for", _spy_build)
    _build(monkeypatch, _settings(GEMINI_MODEL_SUMMARY="summary-model"))
    assert built_models == ["summary-model"]


def test_same_summary_model_reuses_main_client(monkeypatch):
    monkeypatch.setattr(
        worker,
        "build_gemini_for",
        lambda *a: (_ for _ in ()).throw(AssertionError("不應另建 client")),
    )
    scheduler, _core = _build(monkeypatch, _settings())
    assert scheduler is not None


def test_consolidation_job_consolidates_then_summarizes(monkeypatch):
    consolidated: list[str] = []
    summarized: list[str] = []
    monkeypatch.setattr(
        worker, "run_consolidation", lambda elder_id, **kw: consolidated.append(elder_id)
    )
    monkeypatch.setattr(worker, "summarize_day", lambda elder_id, **kw: summarized.append(elder_id))
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1", "e2"])
    _job(scheduler, "daily-consolidation").run()
    assert consolidated == ["e1", "e2"]
    assert summarized == ["e1", "e2"]


def test_summary_failure_does_not_block_consolidation(monkeypatch):
    consolidated: list[str] = []
    monkeypatch.setattr(
        worker, "run_consolidation", lambda elder_id, **kw: consolidated.append(elder_id)
    )

    def _boom(elder_id, **kw):
        raise RuntimeError("摘要掛了")

    monkeypatch.setattr(worker, "summarize_day", _boom)
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1", "e2"])
    _job(scheduler, "daily-consolidation").run()
    assert consolidated == ["e1", "e2"]  # 摘要失敗不影響整理與其他長輩


def test_greeting_pushes_and_records_reminder_log(monkeypatch):
    router = _SpyRouter()
    reminder_logs = _SpyReminderLogs()
    scheduler, _core = _build(
        monkeypatch, _settings(), elders=["e1"], router=router, reminder_logs=reminder_logs
    )
    _job(scheduler, "daily-greeting").run()
    assert [(pt, pid) for pt, pid, _ in router.sent] == [(PrincipalType.ELDER, "e1")]
    assert worker.GREETING_INTENT in router.sent[0][2]
    assert reminder_logs.recorded == [("e1", "proactive-greeting", router.sent[0][2])]


def test_greeting_skips_elder_without_route(monkeypatch):
    router = _SpyRouter(reachable=False)
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1"], router=router)
    _job(scheduler, "daily-greeting").run()
    assert router.sent == []  # 不可達就不生成內容、不投遞


def test_inactivity_cares_only_after_threshold(monkeypatch):
    router = _SpyRouter()
    now_ts = _clock().timestamp()
    # e-old 超過門檻（3 天前）、e-fresh 剛互動過。
    last = {"e-old": now_ts - 4 * 86400, "e-fresh": now_ts - 3600}
    scheduler, _core = _build(
        monkeypatch,
        _settings(),
        elders=["e-old", "e-fresh"],
        router=router,
        last_active=lambda elder_id: last[elder_id],
    )
    _job(scheduler, "inactivity-care").run()
    assert [pid for _, pid, _ in router.sent] == ["e-old"]
    assert worker.INACTIVITY_INTENT in router.sent[0][2]


def test_serve_ticks_until_interrupted(monkeypatch):
    ran: list[int] = []
    scheduler = SimpleNamespace(run_due=lambda: ran.append(1))
    slept: list[int] = []

    def _sleep(seconds: int) -> None:
        slept.append(seconds)
        if len(slept) >= 2:
            raise KeyboardInterrupt

    monkeypatch.setattr(worker.time, "sleep", _sleep)
    with pytest.raises(KeyboardInterrupt):
        worker.serve(scheduler, tick_seconds=30)
    assert len(ran) == 2
    assert slept == [30, 30]


def test_main_builds_serves_and_closes_db(monkeypatch, capsys):
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    db = _FakeDb()
    scheduler = SimpleNamespace(run_due=lambda: None)
    monkeypatch.setattr(worker, "build_scheduler", lambda settings, *, clock: (scheduler, db))
    served: list[tuple] = []
    monkeypatch.setattr(
        worker, "serve", lambda s, *, tick_seconds: served.append((s, tick_seconds))
    )
    assert worker.main() == 0
    assert served == [(scheduler, 60)] or served[0][0] is scheduler
    assert db.closed  # finally 一定關連線
    assert "排程器啟動" in capsys.readouterr().out
