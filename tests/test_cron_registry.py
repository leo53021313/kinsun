"""排程宣告（registry）本身的行為。

⚠️ registry 是「全系統有哪些排程」的唯一真實來源，但真實來源只有在**沒有人能繞過它**
的時候才是真實來源。「實際建出來的 job 是否與宣告一致」由 `test_cron_worker.py` 的
漂移守門測試負責（那裡有現成的假 Core）；本檔守的是宣告本身該有的性質。
"""

import pytest

from kinsun.config import load_settings
from kinsun.cron.registry import (
    GREETING_SCAN_CRON,
    OWNER_RAG_WORKER,
    job_specs,
    rag_refresh_spec,
)
from kinsun.proactive.constants import SLOT_MINUTES

# 讓條件註冊的 job 全部成立的一組設定：兩支音檔清理都要有、RAG 週更也要有。
_FULL_ENV = {
    "DATABASE_URL": "postgresql://x/y",
    "GEMINI_API_KEY": "k",
    "LINE_CHANNEL_SECRET": "s",
    "LINE_CHANNEL_ACCESS_TOKEN": "t",
    "ADMIN_API_KEY": "a",
    "TTS_BACKEND": "dgx",
    "AUDIO_RETENTION_DAYS": "2",
    "SUPABASE_URL": "https://x.supabase.co",
    "SUPABASE_SERVICE_KEY": "sk",
    "RAG_REFRESH_ENABLED": "true",
}


def _settings(**overrides):
    return load_settings({**_FULL_ENV, **overrides})


def test_the_rag_worker_builds_exactly_the_declared_job():
    """RAG Worker 也不得自己取名字：名稱只要與 registry 差一個字，後台就會把一支
    跑得好好的排程誤報成「從未執行」（後台是以 job 名去 scheduler_state 查的）。"""
    spec = rag_refresh_spec(cron="0 3 * * 0")
    declared = [s for s in job_specs(_settings()) if s.owner == OWNER_RAG_WORKER]
    assert declared == [spec]
    assert spec.name == "rag-weekly-refresh"


def test_the_rag_job_is_declared_even_though_another_process_runs_it():
    """這是 2026-07-27 修掉的盲區本身：RAG 週更跑在別的程序，但它必須出現在
    全系統宣告裡——否則後台的排程健康檢查對它完全失明。"""
    names = {s.name for s in job_specs(_settings())}
    assert "rag-weekly-refresh" in names


def test_a_disabled_rag_refresh_is_not_declared():
    """沒開就不該列——把「刻意沒啟用」報成「從未執行」等於製造假警報，
    而假警報會讓人開始忽略這一頁，那就回到停擺十三天沒人發現的原點。"""
    names = {s.name for s in job_specs(_settings(RAG_REFRESH_ENABLED="false"))}
    assert "rag-weekly-refresh" not in names


@pytest.mark.parametrize(
    ("overrides", "absent"),
    [
        ({"AUDIO_RETENTION_DAYS": "0"}, ["audio-cleanup", "inbound-audio-cleanup"]),
        ({"TTS_BACKEND": "bubble"}, ["audio-cleanup"]),
        ({"SUPABASE_URL": "", "SUPABASE_SERVICE_KEY": ""}, ["inbound-audio-cleanup"]),
    ],
)
def test_conditional_jobs_disappear_when_their_setting_is_off(overrides, absent):
    names = {s.name for s in job_specs(_settings(**overrides))}
    for name in absent:
        assert name not in names


def test_the_greeting_scan_aligns_with_the_preference_slots():
    """問候偏好時間只會落在半點（`SLOT_MINUTES`），故掃描必須每半小時一次。

    改成每小時掃，所有存成 xx:30 的偏好都會晚半小時到一小時才被問候——而後台
    仍會顯示她的偏好是 07:30。這兩個值分屬兩個模組，只能靠測試綁在一起。
    """
    assert SLOT_MINUTES == 30
    assert GREETING_SCAN_CRON == "0,30 * * * *"
    spec = next(s for s in job_specs(_settings()) if s.name == "daily-greeting")
    assert spec.cron == GREETING_SCAN_CRON


def test_the_dispatch_tolerance_equals_its_own_due_window():
    """派送遲到超過判定窗＝該送的提醒已永久遺失（窗外不補），故容許量必須等於窗。

    用後台預設的 300 秒，會在提醒**已經掉了**的區間裡仍顯示健康。
    """
    settings = _settings(SCHEDULE_DISPATCH_WINDOW_SECONDS="90")
    spec = next(s for s in job_specs(settings) if s.name == "schedule-dispatch")
    assert spec.max_lateness_seconds == 90.0


def test_only_the_elder_wide_batches_run_in_background():
    """會遍歷全部長輩、逐位呼叫 LLM 的才標背景執行；清理類的幾句 SQL 不該標。

    2026-07-26 實測：39 位長輩的夜間批次同步跑，讓每分鐘的 `schedule-dispatch`
    整整兩分鐘沒有動——長輩再多一些，吃藥提醒就會遲到十幾分鐘。
    """
    background = {s.name for s in job_specs(_settings()) if s.background}
    assert background == {"daily-consolidation", "daily-greeting", "inactivity-care"}
