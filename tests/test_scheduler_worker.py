"""worker 組裝根：build_scheduler 的全 job 接線與閉包行為（M-8 覆蓋補強）。

外部相依與共用物件圖（assemble_core）以假 Core 替換，build_scheduler 自己的
接線邏輯照常執行——驗證「哪些 job 有掛、哪些條件不掛、job 跑起來接對線」。
"""

from __future__ import annotations

import inspect
import logging
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import kinsun.scheduler.worker as worker
from kinsun.accounts.models import PrincipalType
from kinsun.config import load_settings
from kinsun.proactive.greeting_time import update_greeting_time as _real_update_greeting_time
from kinsun.proactive.preferences import FakeGreetingPreferenceStore, GreetingPreference
from kinsun.reports.reminders import FakeReminderLogStore, ReminderLogError
from kinsun.strategies.reflection import reflect_days as _real_reflect_days

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
    """出站路由替身；delivered ＝ send_text 回傳的送達通道數。

    delivered=0 模擬「有綁定通道、但每個通道都送失敗」（LINE token 過期、推播配額
    用罄）：真 router 的 send_text 逐通道吞例外、只回傳成功數，**不會拋**——替身
    的行為必須跟著它，否則測不到「送達 0 通道」這條路徑。
    """

    def __init__(self, *, reachable: bool = True, delivered: int = 1) -> None:
        self.reachable = reachable
        self.delivered = delivered
        self.sent: list[tuple[PrincipalType, str, str]] = []

    def has_route(self, principal_type, principal_id) -> bool:
        return self.reachable

    def send_text(self, principal_type, principal_id, text) -> int:
        self.sent.append((principal_type, principal_id, text))
        return self.delivered


class _UnwritableReminderLogStore(FakeReminderLogStore):
    """record 一律失敗、讀取照常：模擬 reminder_logs 缺 INSERT 權限或持續鎖等待。

    「寫不進去但讀得到」正是最危險的組合——greeted_today 讀得到空清單、恆為 false。
    """

    def record(self, elder_id, kind, content):
        raise ReminderLogError("提醒紀錄存取失敗：permission denied for table reminder_logs")


def _fake_core(
    settings,
    *,
    elders: list[str] | None = None,
    router: _SpyRouter | None = None,
    reminder_logs: FakeReminderLogStore | None = None,
    last_active=None,
    greeting_prefs: FakeGreetingPreferenceStore | None = None,
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
        # 用正牌的 Fake（非自造 spy）：問候 job 的冪等靠 list_for_range 讀 reminder_logs，
        # 只有 record 的替身會讓「今天問候過沒」的接線測不到。
        reminder_logs=reminder_logs if reminder_logs is not None else FakeReminderLogStore(_clock),
        # 夜間批次寫、問候 job 讀（spec 2026-07-16）。
        greeting_prefs=(
            greeting_prefs if greeting_prefs is not None else FakeGreetingPreferenceStore()
        ),
        # 兩根共用收進 Core（✅ 庚-44）。
        risk_events=SimpleNamespace(list_for_elder=lambda elder_id: []),
        summaries=SimpleNamespace(save=lambda *a, **k: None),
        notifications=object(),
        # 每晚反思寫入端（spec 2026-07-14）：worker 應取用 Core 現成的 store，不自建。
        strategies=SimpleNamespace(
            list_for_elder=lambda elder_id, status=None: [],
            record=lambda *a, **k: None,
        ),
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
    summarized: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        worker, "run_consolidation", lambda elder_id, **kw: consolidated.append(elder_id)
    )
    monkeypatch.setattr(
        worker,
        "summarize_day",
        lambda elder_id, **kw: summarized.append((elder_id, kw.get("risk_events") is not None)),
    )
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1", "e2"])
    _job(scheduler, "daily-consolidation").run()
    assert consolidated == ["e1", "e2"]
    # 摘要納 L1（✅ D-10 己-5）：risk_events 讀取端有接上。
    assert summarized == [("e1", True), ("e2", True)]


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


def _binding_spy(record):
    """會驗簽章的 reflect_days 替身：worker 漏傳必填參數時就地 TypeError。

    `lambda elder_id, **kw` 這種寬鬆替身會把 worker 的漏傳照單全收（`max_turns` 刻意
    無預設值），測試照樣全綠，錯留到正式環境每晚炸一次。故此處拿真 `reflect_days` 的
    簽章做 bind——測試替身的寬容度不可以高於它替身的那個函式。
    """
    signature = inspect.signature(_real_reflect_days)

    def _spy(elder_id, **kwargs):
        signature.bind(elder_id, **kwargs)
        record(elder_id, kwargs)

    return _spy


def _stub_nightly(monkeypatch, *, consolidate=None, summarize=None):
    monkeypatch.setattr(worker, "run_consolidation", consolidate or (lambda elder_id, **kw: None))
    monkeypatch.setattr(worker, "summarize_day", summarize or (lambda elder_id, **kw: None))


def test_consolidation_job_reflects_after_summarising(monkeypatch):
    """反思掛進既有夜間批次（spec 2026-07-14）：整理 → 摘要 → 反思，接線與設定要對上。"""
    events: list[tuple[str, str]] = []
    calls: list[dict] = []
    _stub_nightly(
        monkeypatch,
        consolidate=lambda elder_id, **kw: events.append(("整理", elder_id)),
        summarize=lambda elder_id, **kw: events.append(("摘要", elder_id)),
    )
    monkeypatch.setattr(
        worker,
        "reflect_days",
        _binding_spy(
            lambda elder_id, kwargs: (events.append(("反思", elder_id)), calls.append(kwargs))
        ),
    )
    scheduler, core = _build(monkeypatch, _settings(), elders=["e1"])
    _job(scheduler, "daily-consolidation").run()

    assert events == [("整理", "e1"), ("摘要", "e1"), ("反思", "e1")]
    kwargs = calls[0]
    assert kwargs["short_term"] is core.memory
    assert kwargs["reminder_logs"] is core.reminder_logs
    assert kwargs["strategies"] is core.strategies  # 取 Core 現成的 store，不自建第二個
    assert kwargs["reflector"] is core.gemini  # 與摘要共用 GEMINI_MODEL_SUMMARY 那一顆
    assert kwargs["lookback_days"] == 7
    assert kwargs["min_observed_days"] == 3
    assert kwargs["max_strategies"] == 15
    assert kwargs["max_turns"] == 600


def test_reflection_can_be_switched_off(monkeypatch):
    """REFLECTION_ENABLED 是緊急關閉開關：關掉後夜間批次不得再呼叫反思。"""
    reflected: list[str] = []
    _stub_nightly(monkeypatch)
    monkeypatch.setattr(
        worker, "reflect_days", _binding_spy(lambda elder_id, kw: reflected.append(elder_id))
    )
    scheduler, _core = _build(monkeypatch, _settings(REFLECTION_ENABLED="false"), elders=["e1"])
    _job(scheduler, "daily-consolidation").run()
    assert reflected == []


def test_reflection_failure_does_not_break_the_batch(monkeypatch, caplog):
    """reflect_days 對 LLM timeout／MemoryStoreError 刻意不設防，防線在 run_one。"""
    consolidated: list[str] = []
    summarized: list[str] = []
    attempted: list[str] = []
    _stub_nightly(
        monkeypatch,
        consolidate=lambda elder_id, **kw: consolidated.append(elder_id),
        summarize=lambda elder_id, **kw: summarized.append(elder_id),
    )

    def _boom(elder_id, **kw):
        attempted.append(elder_id)
        raise RuntimeError("gemini 掛了")

    monkeypatch.setattr(worker, "reflect_days", _boom)
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1", "e2"])
    with caplog.at_level(logging.WARNING):
        _job(scheduler, "daily-consolidation").run()  # 不應拋出

    assert consolidated == ["e1", "e2"]  # 反思失敗不影響長期記憶整理……
    assert summarized == ["e1", "e2"]  # ……也不影響家屬摘要
    assert attempted == ["e1", "e2"]  # 一位長輩的 LLM timeout 不得炸掉整批長輩的反思
    assert any("每晚反思失敗" in r.getMessage() for r in caplog.records)
    # 失敗必須收在 run_one 內：少了 try/except 時 fanout 會在外層補一筆 ERROR，把整位
    # 長輩的夜間批次標成失敗——縱使整理與摘要其實都做完了，值班的人會查錯方向。
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_summary_failure_does_not_block_reflection(monkeypatch):
    """三個批次互不拖累：摘要掛了，今晚照樣要學。"""
    reflected: list[str] = []

    def _boom(elder_id, **kw):
        raise RuntimeError("摘要掛了")

    _stub_nightly(monkeypatch, summarize=_boom)
    monkeypatch.setattr(
        worker, "reflect_days", _binding_spy(lambda elder_id, kw: reflected.append(elder_id))
    )
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1"])
    _job(scheduler, "daily-consolidation").run()
    assert reflected == ["e1"]


def _update_binding_spy(record):
    """會驗簽章的 update_greeting_time 替身（理由同 _binding_spy）。

    lag_tolerance_minutes 是 Task D 後補上的必填參數，寬鬆替身會把漏傳照單全收。
    """
    signature = inspect.signature(_real_update_greeting_time)

    def _spy(elder_id, **kwargs):
        signature.bind(elder_id, **kwargs)
        record(elder_id, kwargs)

    return _spy


def test_the_nightly_batch_updates_the_greeting_time_last(monkeypatch):
    """自適應問候時間掛進夜間批次第四步：整理 → 摘要 → 反思 → 問候時間。"""
    events: list[tuple[str, str]] = []
    calls: list[dict] = []
    _stub_nightly(
        monkeypatch,
        consolidate=lambda elder_id, **kw: events.append(("整理", elder_id)),
        summarize=lambda elder_id, **kw: events.append(("摘要", elder_id)),
    )
    monkeypatch.setattr(
        worker, "reflect_days", _binding_spy(lambda elder_id, kw: events.append(("反思", elder_id)))
    )
    monkeypatch.setattr(
        worker,
        "update_greeting_time",
        _update_binding_spy(
            lambda elder_id, kwargs: (events.append(("問候時間", elder_id)), calls.append(kwargs))
        ),
    )
    scheduler, core = _build(monkeypatch, _settings(), elders=["e1"])
    _job(scheduler, "daily-consolidation").run()

    assert events == [("整理", "e1"), ("摘要", "e1"), ("反思", "e1"), ("問候時間", "e1")]
    kwargs = calls[0]
    assert kwargs["short_term"] is core.memory
    assert kwargs["prefs"] is core.greeting_prefs  # 取 Core 現成的 store，不自建第二個
    assert kwargs["default_hour"] == 8
    assert kwargs["lookback_days"] == 14
    assert kwargs["min_sample_days"] == 5
    assert kwargs["earliest_hour"] == 6
    assert kwargs["latest_hour"] == 11
    assert kwargs["max_shift_minutes"] == 30
    assert kwargs["lag_tolerance_minutes"] == 60


def test_the_greeting_time_update_can_be_switched_off(monkeypatch):
    """PROACTIVE_GREETING_ADAPTIVE_ENABLED 是緊急關閉開關：關掉後不得再計算。"""
    updated: list[str] = []
    _stub_nightly(monkeypatch)
    monkeypatch.setattr(
        worker,
        "update_greeting_time",
        _update_binding_spy(lambda elder_id, kw: updated.append(elder_id)),
    )
    scheduler, _core = _build(
        monkeypatch, _settings(PROACTIVE_GREETING_ADAPTIVE_ENABLED="false"), elders=["e1"]
    )
    _job(scheduler, "daily-consolidation").run()
    assert updated == []


def test_switching_off_reflection_does_not_switch_off_the_greeting_time(monkeypatch):
    """兩個開關互相獨立——反思關掉時問候時間照算。

    這是 run_one 的結構陷阱：反思那段原本以 `if not enabled: return` 提早結束整個
    函式，把第四步接在它後面會讓 REFLECTION_ENABLED=false 連帶關掉問候時間計算，
    而兩者在設定上毫無關係。
    """
    updated: list[str] = []
    _stub_nightly(monkeypatch)
    monkeypatch.setattr(
        worker,
        "update_greeting_time",
        _update_binding_spy(lambda elder_id, kw: updated.append(elder_id)),
    )
    scheduler, _core = _build(monkeypatch, _settings(REFLECTION_ENABLED="false"), elders=["e1"])
    _job(scheduler, "daily-consolidation").run()
    assert updated == ["e1"]


def test_greeting_time_failure_does_not_break_the_batch(monkeypatch, caplog):
    """問候時間算不出來，就只是「今晚不調時間」，不該連累前三步或其他長輩。"""
    consolidated: list[str] = []
    summarized: list[str] = []
    reflected: list[str] = []
    attempted: list[str] = []
    _stub_nightly(
        monkeypatch,
        consolidate=lambda elder_id, **kw: consolidated.append(elder_id),
        summarize=lambda elder_id, **kw: summarized.append(elder_id),
    )
    monkeypatch.setattr(
        worker, "reflect_days", _binding_spy(lambda elder_id, kw: reflected.append(elder_id))
    )

    def _boom(elder_id, **kw):
        attempted.append(elder_id)
        raise RuntimeError("記憶庫掛了")

    monkeypatch.setattr(worker, "update_greeting_time", _boom)
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1", "e2"])
    with caplog.at_level(logging.WARNING):
        _job(scheduler, "daily-consolidation").run()  # 不應拋出

    assert consolidated == ["e1", "e2"]
    assert summarized == ["e1", "e2"]
    assert reflected == ["e1", "e2"]
    assert attempted == ["e1", "e2"]  # 一位長輩失敗不得炸掉整批
    assert any("問候時間計算失敗" in r.getMessage() for r in caplog.records)
    # 失敗必須收在 run_one 內，否則 fanout 會把整位長輩的夜間批次標成 ERROR。
    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_greeting_pushes_and_records_reminder_log(monkeypatch):
    router = _SpyRouter()
    reminder_logs = FakeReminderLogStore(_clock)
    scheduler, _core = _build(
        monkeypatch, _settings(), elders=["e1"], router=router, reminder_logs=reminder_logs
    )
    _job(scheduler, "daily-greeting").run()
    assert [(pt, pid) for pt, pid, _ in router.sent] == [(PrincipalType.ELDER, "e1")]
    assert worker.GREETING_INTENT in router.sent[0][2]
    assert reminder_logs.recorded == [("e1", "proactive-greeting", router.sent[0][2])]


def test_it_does_not_greet_her_twice_in_the_same_day(monkeypatch):
    """job 每半小時跑一次（spec 2026-07-16），冪等全靠 reminder_logs——跑兩次只能問候一次。

    這條測的是 greeted_today 這個閉包本身：它讀的是真的 reminder_logs，而問候寫的
    也是真的 reminder_logs。少了它，「每半小時掃描」會變成「每半小時轟炸長輩一次」。
    """
    router = _SpyRouter()
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1"], router=router)
    job = _job(scheduler, "daily-greeting")
    job.run()
    job.run()  # 下一次掃描（或 worker 重啟後的補跑）
    assert len(router.sent) == 1


def test_a_greeting_it_cannot_book_is_never_sent(monkeypatch):
    """記不進帳就不問候——問候的冪等帳本就是 reminder_logs（spec 2026-07-16）。

    這條釘的是本任務親手造出來的風險：reminder_logs 從「觀測帳」升格成「冪等帳本」
    之後，用 safe_record 吞掉寫入失敗＝greeted_today 永遠是 false。cron 是
    `0,30 * * * *`，於是從她的偏好時間起每半小時推一則早安到當天結束（約 30 則），
    每則還燒一次 LLM。32 輪 ≈ 16 小時的掃描，涵蓋一整個白天。

    記帳失敗必須讓它冒到 fanout ＝ 跳過本輪、30 分鐘後重試，與 job 已宣告的
    「寧可漏問候，不可重複轟炸」同向。
    """
    router = _SpyRouter()
    scheduler, _core = _build(
        monkeypatch,
        _settings(),
        elders=["e1"],
        router=router,
        reminder_logs=_UnwritableReminderLogStore(_clock),
    )
    job = _job(scheduler, "daily-greeting")
    for _ in range(32):
        job.run()
    assert not router.sent, f"記帳失敗，卻對她推了 {len(router.sent)} 則問候"


def test_a_greeting_that_reached_nobody_is_attributable(monkeypatch, caplog):
    """送達 0 通道仍要記帳（at-most-once 不重推），但必須留下可歸因的痕跡。

    LINE token 過期／推播配額用罄時 send_text 回 0、不拋，帳照記、greeted_today
    變 True——她整天收不到問候，後台帳上卻顯示「已問候」。不重推是政策（正確），
    但「這一則問候等於沒送出」這個結論必須查得到，否則沒人知道要去查 token。
    """
    router = _SpyRouter(delivered=0)
    reminder_logs = FakeReminderLogStore(_clock)
    scheduler, _core = _build(
        monkeypatch, _settings(), elders=["e1"], router=router, reminder_logs=reminder_logs
    )
    with caplog.at_level(logging.WARNING):
        _job(scheduler, "daily-greeting").run()

    assert len(router.sent) == 1  # 有試著送
    assert len(reminder_logs.recorded) == 1  # 帳照記（at-most-once：不重推）
    assert any("零通道送達" in r.getMessage() for r in caplog.records)


def test_it_greets_at_her_own_time_rather_than_the_global_hour(monkeypatch):
    """接線驗證：問候 job 真的讀得到夜間批次寫的偏好。

    e-late 的偏好 11:00 還沒到（現在 09:00）→ 不問候；e-early 的 06:30 早就過了 → 問候。
    """
    router = _SpyRouter()
    prefs = FakeGreetingPreferenceStore()
    prefs.save(GreetingPreference("e-late", 11, 0, 0.0, 7, 660))
    prefs.save(GreetingPreference("e-early", 6, 30, 0.0, 7, 390))
    scheduler, _core = _build(
        monkeypatch,
        _settings(),
        elders=["e-late", "e-early"],
        router=router,
        greeting_prefs=prefs,
    )
    _job(scheduler, "daily-greeting").run()
    assert [pid for _, pid, _ in router.sent] == ["e-early"]


def test_the_kill_switch_makes_everyone_fall_back_to_the_global_hour(monkeypatch):
    """PROACTIVE_GREETING_ADAPTIVE_ENABLED=false 必須讓「已經存在的偏好」也失效。

    只擋住夜間計算是不夠的：緊急關閉時 greeting_preferences 裡還躺著上次算出來的
    時間，問候 job 若照樣讀，關掉開關等於什麼都沒關——長輩仍在她的自適應時間被問候。
    開關要能真的回退到 PROACTIVE_GREETING_HOUR，才叫緊急關閉。
    """
    router = _SpyRouter()
    prefs = FakeGreetingPreferenceStore()
    prefs.save(GreetingPreference("e-late", 11, 0, 0.0, 7, 660))  # 11:00 > 現在 09:00
    scheduler, _core = _build(
        monkeypatch,
        _settings(PROACTIVE_GREETING_ADAPTIVE_ENABLED="false"),
        elders=["e-late"],
        router=router,
        greeting_prefs=prefs,
    )
    _job(scheduler, "daily-greeting").run()
    # 關掉後偏好不算數：全域 08:00 已過 → 照樣問候。
    assert [pid for _, pid, _ in router.sent] == ["e-late"]


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
