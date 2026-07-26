"""worker 組裝根：build_scheduler 的全 job 接線與閉包行為（M-8 覆蓋補強）。

外部相依與共用物件圖（assemble_core）以假 Core 替換，build_scheduler 自己的
接線邏輯照常執行——驗證「哪些 job 有掛、哪些條件不掛、job 跑起來接對線」。
"""

from __future__ import annotations

import inspect
import logging
import signal
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

import kinsun.cron.worker as worker
from kinsun.accounts.models import PrincipalType
from kinsun.agent import Recall
from kinsun.config import load_settings
from kinsun.news.store import FakeNewsStore
from kinsun.proactive.greeting_time import update_greeting_time as _real_update_greeting_time
from kinsun.proactive.preferences import FakeGreetingPreferenceStore, GreetingPreference
from kinsun.reports.reminders import (
    REMINDER_KIND_APPOINTMENT,
    REMINDER_KIND_MEDICATION,
    FakeReminderLogStore,
    ReminderLogError,
)
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
    # D-76 P2：四個用藥 job ＋ 一個回診 job 併成一個每分鐘的派送 job。
    # P3 換掉家屬寫入端後，過渡期的對帳 job 已移除。
    "schedule-dispatch",
    "observability-cleanup",
    "news-crawl",
    "news-cleanup",
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
    news: FakeNewsStore | None = None,
    news_mentions=None,
    long_term=None,
):
    from kinsun.news.mentions import FakeNewsMentionStore

    elders = elders if elders is not None else []
    return SimpleNamespace(
        settings=settings,
        db=_FakeDb(),
        gemini=_FakeLLM(),
        # 預設無 search 方法（AttributeError）→ 興趣檢索走降級路徑，不影響問候。
        long_term=long_term if long_term is not None else object(),
        messenger=object(),
        router=router or _SpyRouter(),
        accounts=SimpleNamespace(
            get_elder=lambda elder_id: None,
            guardians_of=lambda elder_id: [],
        ),
        # 舊表（D-76 P2 之後只剩對帳橋接讀它們，P3 移除）。
        med_store=SimpleNamespace(list_for_slot=lambda slot: []),
        appt_store=SimpleNamespace(list_for_date=lambda date_str: []),
        # 統一排程派送 job 的資料來源；本檔的斷言都在問候／失聯／夜間批次，
        # 故一律回空，讓派送 job 每輪什麼都不做。
        schedule_store=SimpleNamespace(
            list_due_once=lambda **kw: [],
            list_due_repeating=lambda **kw: [],
            mark_fired=lambda *a, **k: None,
            mark_settled=lambda *a, **k: None,
        ),
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
        # 話題新聞（spec 2026-07-20）：爬取／清除 job 寫；D-74 消費端起問候不再直讀。
        news=news if news is not None else FakeNewsStore(),
        # 提及紀錄（D-74 消費端）：get_news 寫、清理 job 清。
        news_mentions=news_mentions if news_mentions is not None else FakeNewsMentionStore(),
        # 兩根共用收進 Core（✅ 庚-44）。
        risk_events=SimpleNamespace(list_for_elder=lambda elder_id: []),
        # get_for_date：主動推播讀「她上次開口那天」的摘要當檢索關鍵字＋注入
        # （spec 2026-07-17）。預設回 None＝那天沒摘要，主動推播據此退回無脈絡行為。
        summaries=SimpleNamespace(save=lambda *a, **k: None, get_for_date=lambda *a, **k: None),
        notifications=object(),
        # 每晚反思寫入端（spec 2026-07-14）：worker 應取用 Core 現成的 store，不自建。
        strategies=SimpleNamespace(
            list_for_elder=lambda elder_id, status=None: [],
            record=lambda *a, **k: None,
        ),
        agent=SimpleNamespace(proactive=lambda elder_id, intent, *, recall=None: f"主動：{intent}"),
    )


def _settings(**overrides):
    return load_settings({**_BASE_ENV, **overrides})


def _clock() -> datetime:
    return datetime(2026, 7, 10, 9, 0, tzinfo=ZoneInfo("Asia/Taipei"))


def _ts(year: int, month: int, day: int) -> float:
    """那天早上 9 點的 epoch 秒——當 last_active（她最後開口的時刻）用。"""
    return datetime(year, month, day, 9, 0, tzinfo=ZoneInfo("Asia/Taipei")).timestamp()


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

    def _spy_build(settings, model, *, client_wrapper=None):
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
    from kinsun.proactive.jobs import GREETING_INTENT

    assert GREETING_INTENT in router.sent[0][2]
    assert "星期" in router.sent[0][2]  # intent 織入日期素材（2026-07-17 問候多樣性）
    assert reminder_logs.recorded == [("e1", "proactive-greeting", router.sent[0][2])]


def test_greeting_intent_guides_get_news_instead_of_weaving(monkeypatch):
    """問候改工具引導（D-74 消費端，2026-07-25）：intent 提示用 get_news、
    不再由 worker 直讀新聞表織入標題——新聞故障面因此整個移出問候路徑。"""
    router = _SpyRouter()
    scheduler, _core = _build(monkeypatch, _settings(), elders=["e1"], router=router)
    _job(scheduler, "daily-greeting").run()
    intent = router.sent[0][2]
    assert "get_news" in intent
    assert "最近的新聞有" not in intent


def test_news_cleanup_job_purges_items_and_mentions(monkeypatch):
    """清理 job 同一把保留天數清 news_items 與 news_mentions（D-74 消費端）。"""
    from kinsun.news.mentions import FakeNewsMentionStore
    from kinsun.news.models import NewsItem

    news = FakeNewsStore()
    old_at = _clock().timestamp() - 15 * 86400  # 超過預設保留 14 天
    news.save(
        NewsItem(
            news_item_id="n-old",
            source_id="mohw",
            title="過期新聞",
            url="https://example.com/n-old",
            publisher="衛生福利部",
            content="內文",
            published_at=old_at,
            retrieved_at=old_at,
        )
    )
    mentions = FakeNewsMentionStore()
    mentions.record("e1", "n-old", mentioned_at=old_at)
    scheduler, _core = _build(
        monkeypatch, _settings(), elders=["e1"], news=news, news_mentions=mentions
    )
    _job(scheduler, "news-cleanup").run()
    assert news.list_recent(since=0.0) == []
    assert mentions.list_for_elder("e1") == set()


def test_greeting_carries_summary_of_the_day_she_last_spoke(monkeypatch):
    """問候前先讀「她上次開口那天」的摘要餵給 agent（spec 2026-07-17）。

    _clock() 是 2026-07-10；她昨天（07-09）講過話，故讀 07-09 的摘要、距今 1 天。
    刻意不用「今天減一天」定位：她可能好幾天沒開口（見下一條），那時昨天的摘要
    若存在也只是金孫自言自語的紀錄——主動推播每天都會寫 assistant turn。
    """
    calls: list[tuple[str, object]] = []
    scheduler, core = _build(
        monkeypatch, _settings(), elders=["e1"], last_active=lambda elder_id: _ts(2026, 7, 9)
    )
    core.summaries.get_for_date = lambda elder_id, date: SimpleNamespace(
        content=f"{elder_id} 在 {date} 聊到孫子"
    )
    core.agent.proactive = lambda elder_id, intent, *, recall=None: (
        calls.append((elder_id, recall)) or "阿嬤早"
    )

    _job(scheduler, "daily-greeting").run()

    assert calls == [("e1", Recall("e1 在 2026-07-09 聊到孫子", 1))]


def test_recall_reaches_back_to_her_last_spoken_day_not_yesterday(monkeypatch):
    """她五天沒開口：要拿的是 07-05（她最後講話那天）的摘要，並告知已隔 5 天。

    這是真 Gemini 探針揪出的設計錯：想念推播的觸發條件是「≥2 天沒開口」，與
    「昨天有她的對話」互斥——照昨天去讀，這條路永遠是 None，等於沒修。
    """
    calls: list[object] = []
    asked: list[str] = []
    scheduler, core = _build(
        monkeypatch, _settings(), elders=["e1"], last_active=lambda elder_id: _ts(2026, 7, 5)
    )

    def _summary(elder_id, date):
        asked.append(date)
        return SimpleNamespace(content="阿嬤聊到孫子要來")

    core.summaries.get_for_date = _summary
    core.agent.proactive = lambda elder_id, intent, *, recall=None: (
        calls.append(recall) or "阿嬤，好久沒聽到您的聲音了"
    )

    _job(scheduler, "inactivity-care").run()

    assert asked == ["2026-07-05"]
    assert calls == [Recall("阿嬤聊到孫子要來", 5)]


def test_recall_is_none_when_she_has_never_spoken(monkeypatch):
    """新長輩：沒有 last_active 就無從定位摘要日，退回無脈絡問候。"""
    calls: list[object] = []
    scheduler, core = _build(monkeypatch, _settings(), elders=["e1"])  # last_active 預設 None

    def _never_called(elder_id, date):
        raise AssertionError("沒有 last_active 就不該去查摘要")

    core.summaries.get_for_date = _never_called
    core.agent.proactive = lambda elder_id, intent, *, recall=None: calls.append(recall) or "阿嬤早"

    _job(scheduler, "daily-greeting").run()

    assert calls == [None]


def test_inactivity_care_carries_recall_too(monkeypatch):
    """想念推播與問候共用同一條推播路徑，一起吃到脈絡（Leo 核定：兩個一起修）。

    「想念你」這種話比問候更需要記得她上次講什麼，否則更像罐頭。
    """
    calls: list[tuple[str, object]] = []
    scheduler, core = _build(
        monkeypatch, _settings(), elders=["e1"], last_active=lambda elder_id: _ts(2026, 7, 5)
    )
    core.summaries.get_for_date = lambda elder_id, date: SimpleNamespace(content="她提到膝蓋痛")
    core.agent.proactive = lambda elder_id, intent, *, recall=None: (
        calls.append((intent, recall)) or "阿嬤，好幾天沒聽到您的聲音了"
    )

    _job(scheduler, "inactivity-care").run()

    assert calls == [(worker.INACTIVITY_INTENT, Recall("她提到膝蓋痛", 5))]


def test_greeting_survives_summary_read_failure(monkeypatch, caplog):
    """摘要讀取失敗只能降級成沒有脈絡，不可擋下問候。

    與既有的問候偏好讀取失敗同向（jobs.py）：降級成本功能之前的行為，
    比整批長輩沒人理她好。
    """
    router = _SpyRouter()
    scheduler, core = _build(
        monkeypatch,
        _settings(),
        elders=["e1"],
        router=router,
        last_active=lambda elder_id: _ts(2026, 7, 9),
    )

    def _boom(elder_id, date):
        raise RuntimeError("摘要表掛了")

    core.summaries.get_for_date = _boom

    with caplog.at_level(logging.WARNING):
        _job(scheduler, "daily-greeting").run()  # 不應拋出

    assert [(pt, pid) for pt, pid, _ in router.sent] == [(PrincipalType.ELDER, "e1")]
    assert any("摘要讀取失敗" in r.getMessage() for r in caplog.records)


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


def test_a_morning_medication_log_must_not_count_as_a_greeting(monkeypatch):
    """用藥／回診提醒不是問候——greeted_today 的 kind 濾網是安全關鍵，不可省。

    四種提醒共用同一張 reminder_logs（刻意設計，見 reports/reminders.py），而問候的
    冪等靠 greeted_today 讀這張表。濾網一旦失效（或日後被「順手簡化」成「今天有紀錄
    就算問候過」），08:00 的用藥提醒（MEDICATION_MORNING_HOUR 預設 8）與回診提醒
    （APPOINTMENT_REMINDER_HOUR 預設 8）都會被認成問候——兩者都落在問候護軌
    [6, 11] 內，於是**所有吃早藥的長輩從此再也收不到問候，且完全靜默**：沒有例外、
    沒有 warning，後台只看得到「今天沒問候她」這個結果。

    其餘 worker 測試的 reminder_logs 都從空的開始、且只有問候會寫入，故沒有任何一條
    測得到這個濾網——這條專門補那個缺口。
    """
    router = _SpyRouter()
    # 提醒寫在今天 08:00（兩者的預設時間），問候 job 09:00 才掃描：同一天、同一張表。
    now = _clock().replace(hour=8)
    logs = FakeReminderLogStore(lambda: now)
    logs.record("e1", REMINDER_KIND_MEDICATION, "早上用藥：血壓藥")
    logs.record("e1", REMINDER_KIND_APPOINTMENT, "明天回診：心臟科")
    now = _clock()  # 閉包捕獲變數本身：其後問候自己的記帳落在 09:00
    scheduler, _core = _build(
        monkeypatch, _settings(), elders=["e1"], router=router, reminder_logs=logs
    )
    _job(scheduler, "daily-greeting").run()
    assert [pid for _, pid, _ in router.sent] == ["e1"], (
        "用藥／回診提醒被誤判成『今天問候過了』——吃早藥的長輩再也收不到問候"
    )


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


def test_a_care_message_still_goes_out_when_the_ledger_is_down(monkeypatch):
    """失聯關心不因記帳失敗而不送——與問候的政策**刻意相反**，不可統一。

    兩條路徑寫的是同一張 reminder_logs，但那筆紀錄的角色不同：

    * 問候（ledger=True）：每半小時掃描一次，冪等全靠 greeted_today 讀這張表——
      記不進去 → greeted_today 恆為 false → 一天約 30 則。記帳是安全關鍵，
      故先記帳、記不了就不推。
    * 失聯關心（ledger=False）：每天一次的 cron（inactivity-care），冪等由 cron
      自己保證、不讀這張表。這筆紀錄是**純觀測**（只供健康報告），拿一個觀測寫入
      去擋關心推播＝她已經好幾天沒消息了，卻因為報表寫不進去而沒人問候她。

    少了這條，日後有人「順手統一兩條路徑」（讓失聯關心也走 ledger）會全綠通過。
    """
    router = _SpyRouter()
    now_ts = _clock().timestamp()
    scheduler, _core = _build(
        monkeypatch,
        _settings(),
        elders=["e-old"],
        router=router,
        last_active=lambda elder_id: now_ts - 4 * 86400,
        reminder_logs=_UnwritableReminderLogStore(_clock),
    )
    _job(scheduler, "inactivity-care").run()
    assert [pid for _, pid, _ in router.sent] == ["e-old"], (
        "記帳失敗擋掉了失聯關心——那筆 reminder_logs 只是觀測，不是冪等帳本"
    )


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
        # watchdog=False：看門狗也會呼叫 time.sleep，開著會污染這條測試的計數
        worker.serve(scheduler, tick_seconds=30, watchdog=False)
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
        worker,
        "serve",
        lambda s, *, tick_seconds, heartbeat=None, heartbeat_path=None: served.append(
            (s, tick_seconds)
        ),
    )
    assert worker.main() == 0
    assert served == [(scheduler, 60)] or served[0][0] is scheduler
    assert db.closed  # finally 一定關連線
    assert "排程器啟動" in capsys.readouterr().out


def test_greeting_weaves_interests_from_long_term(monkeypatch):
    """問候前從長期記憶檢索興趣線索織入 intent（Leo 2026-07-25 興趣驅動挑題）。"""
    from kinsun.memory.models import MemoryItem

    class _StubLongTerm:
        def search(self, elder_id, query, *, top_k=None):
            assert "興趣" in query  # 檢索詞明確以興趣為目標
            return [MemoryItem(text="喜歡園藝，常照顧陽台盆栽")]

    router = _SpyRouter()
    scheduler, _core = _build(
        monkeypatch, _settings(), elders=["e1"], router=router, long_term=_StubLongTerm()
    )
    _job(scheduler, "daily-greeting").run()
    intent = router.sent[0][2]
    assert "喜歡園藝" in intent


def test_interest_lookup_failure_does_not_block_greeting(monkeypatch, caplog):
    """興趣檢索失敗只能降級成沒有興趣提示，不可擋下問候（與摘要讀取失敗同向）。"""

    class _ExplodingLongTerm:
        def search(self, elder_id, query, *, top_k=None):
            raise RuntimeError("mem0 掛了")

    router = _SpyRouter()
    scheduler, _core = _build(
        monkeypatch, _settings(), elders=["e1"], router=router, long_term=_ExplodingLongTerm()
    )
    with caplog.at_level(logging.WARNING):
        _job(scheduler, "daily-greeting").run()  # 不應拋出
    assert [(pt, pid) for pt, pid, _ in router.sent] == [(PrincipalType.ELDER, "e1")]
    assert "興趣可能包含" not in router.sent[0][2]


# --- 看門狗（2026-07-26 全流程模擬實測：排程器活著但停止推進）---


def test_the_watchdog_kills_a_stalled_scheduler():
    """tick 停止推進超過門檻就自殺，交給 systemd 的 Restart=always 撿起來。

    ⚠️ 這一層刻意不賭任何一種診斷：不論卡在 DB、mem0 還是別處，只看「有沒有在動」。
    實測那次假死，程序活著、日誌零成長、狀態頁顯示 RUNNING，七小時沒有人發現。
    """
    exits: list[int] = []
    stale = [time.monotonic() - 9999]  # 上次推進是很久以前
    with pytest.raises(RuntimeError):  # 用例外代替 os._exit，測試才停得下來

        def _exit(code: int) -> None:
            exits.append(code)
            raise RuntimeError("stop")

        worker._watchdog(stale, stall_seconds=0.4, exit_now=_exit)
    assert exits == [1]


def test_the_watchdog_covers_startup_not_just_the_tick_loop(monkeypatch):
    """看門狗必須在 build_scheduler **之前**就開始計時。

    2026-07-26 23:00 現場：排程器當天重啟六次全部卡在啟動階段（啟動橫幅一次都沒印出來，
    `schedule-dispatch` 停在 14:05 不動）。看門狗若只包在 serve() 裡，這一整類假死一次
    也攔不到——因為 tick 迴圈根本還沒開始跑。
    """
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    order: list[str] = []
    monkeypatch.setattr(
        worker,
        "start_watchdog",
        lambda *, stall_seconds: (order.append("watchdog"), [time.monotonic()])[1],
    )

    def _build(settings, *, clock):
        order.append("build_scheduler")
        return SimpleNamespace(run_due=lambda: None), _FakeDb()

    monkeypatch.setattr(worker, "build_scheduler", _build)
    monkeypatch.setattr(
        worker, "serve", lambda s, *, tick_seconds, heartbeat=None, heartbeat_path=None: None
    )
    assert worker.main() == 0
    assert order == ["watchdog", "build_scheduler"], (
        "看門狗晚於 build_scheduler 啟動＝對啟動階段的假死失明"
    )


def test_main_registers_a_stack_dump_signal(monkeypatch):
    """`kill -USR1` 要能把全執行緒堆疊倒進日誌。

    ⚠️ 沒有這條，假死時就只能靠 py-spy——而 DGX 的 ptrace_scope=1 讓 py-spy 需要 root，
    2026-07-26 現場就是因此拿不到任何 Python 堆疊，只知道它卡住、不知道卡在哪。
    """
    if not hasattr(signal, "SIGUSR1"):
        pytest.skip("此平台沒有 SIGUSR1")
    for key, value in _BASE_ENV.items():
        monkeypatch.setenv(key, value)
    registered: list[int] = []
    monkeypatch.setattr(
        worker.faulthandler,
        "register",
        lambda sig, all_threads=True, chain=True: registered.append(sig),
    )
    monkeypatch.setattr(
        worker, "build_scheduler", lambda settings, *, clock: (SimpleNamespace(), _FakeDb())
    )
    monkeypatch.setattr(
        worker, "serve", lambda s, *, tick_seconds, heartbeat=None, heartbeat_path=None: None
    )
    assert worker.main() == 0
    assert registered == [signal.SIGUSR1]


def test_heartbeat_file_lets_status_tell_frozen_from_alive(tmp_path):
    """心跳檔＝狀態頁分辨「行程活著」與「迴圈凍住」的唯一依據（假死七小時全程 RUNNING）。"""
    path = tmp_path / "run" / "scheduler.heartbeat"
    worker.write_heartbeat(path)
    written = float(path.read_text(encoding="utf-8").strip())
    assert abs(written - time.time()) < 5
    assert not (tmp_path / "run" / "scheduler.heartbeat.tmp").exists(), "暫存檔沒清掉"


def test_heartbeat_failure_never_stops_the_tick_loop(tmp_path, caplog):
    """心跳只是觀測。寫不進去要照跑，而且不可以每分鐘刷一行把真錯誤淹掉。"""
    worker._heartbeat_warned[0] = False
    blocked = tmp_path / "not-a-dir"
    blocked.write_text("我是檔案不是目錄", encoding="utf-8")
    target = blocked / "scheduler.heartbeat"
    with caplog.at_level(logging.WARNING):
        worker.write_heartbeat(target)  # 不應拋出
        worker.write_heartbeat(target)
        worker.write_heartbeat(target)
    assert sum("心跳檔寫入失敗" in r.message for r in caplog.records) == 1, "重複警告會變成雜訊"
    worker._heartbeat_warned[0] = False


def test_the_watchdog_leaves_a_healthy_scheduler_alone():
    exits: list[int] = []
    fresh = [time.monotonic()]
    stop = []

    def _exit(code: int) -> None:  # pragma: no cover - 不該被呼叫
        exits.append(code)

    def _sleep(_seconds: float) -> None:
        stop.append(1)
        if len(stop) >= 2:
            raise RuntimeError("測試結束")

    original = worker.time.sleep
    worker.time.sleep = _sleep
    try:
        with pytest.raises(RuntimeError):
            worker._watchdog(fresh, stall_seconds=0.4, exit_now=_exit)
    finally:
        worker.time.sleep = original
    assert exits == []


def test_jobs_that_fan_out_over_every_elder_run_in_the_background(monkeypatch):
    """遍歷全部長輩的 job 必須標成背景，清理類的必須不標。

    ⚠️ 判準是「耗時會不會隨長輩人數成長」。2026-07-26 實測：39 位長輩的夜間批次
    讓每分鐘該派送的 `schedule-dispatch` 停了兩分鐘——同步跑會把整輪掃描卡住，
    而卡住的是長輩的吃藥提醒。清理類的 job 只是幾句 SQL，丟背景只是多開執行緒。
    """
    scheduler, _core = _build(monkeypatch, _settings())
    background = {j.name for j in scheduler._jobs if j.background}
    assert background == {"daily-consolidation", "daily-greeting", "inactivity-care"}
    assert _job(scheduler, "schedule-dispatch").background is False, (
        "每分鐘的提醒派送丟到背景，就失去『這一輪一定跑完』的保證"
    )
