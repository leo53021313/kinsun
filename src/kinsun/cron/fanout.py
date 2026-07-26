"""扇出執行器：每天某點遍歷一個母體，逐筆隔離失敗。"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable
from typing import TypeVar

from kinsun import tracing
from kinsun.cron.scheduler import Job
from kinsun.llm import is_retryable_llm_error

logger = logging.getLogger("kinsun.cron")

T = TypeVar("T")

# 配額退避的節奏。Gemini 回傳體的 retryDelay 實測是 0～29 秒（logs/scheduler.log），
# 指數退避 1→2→4… 在三次之內就能跨過多數的短限流，又不會把夜間批次拖太久。
_RETRY_BASE_BACKOFF_SECONDS = 1.0
_RETRY_MAX_BACKOFF_SECONDS = 30.0


def fanout_job(  # noqa: UP047
    *,
    name: str,
    cron: str,
    population: Callable[[], Iterable[T]],
    action: Callable[[T], None],
    item_id: Callable[[T], str] = str,
    max_lateness_seconds: float | None = None,
    retry_quota_attempts: int = 0,
    sleep: Callable[[float], None] = time.sleep,
    logger: logging.Logger = logger,
) -> Job:
    """組一個 cron job：遍歷 population()，對每筆呼叫 action，逐筆隔離失敗。

    過濾/守門請在 action 內提早 return；母體前處理（分組等）請在 population 內完成。

    `retry_quota_attempts`＝逐筆遇到配額／限流錯誤時最多嘗試幾次（含第一次），退避
    1、2、4…秒（上限 `_RETRY_MAX_BACKOFF_SECONDS`）。

    ⚠️ **預設 0＝不重試，這是刻意的**：問候與提醒 job 重試會讓長輩收到**重複訊息**。
    只有本身冪等的 job 才可以開——實際開的只有 `daily-consolidation`（已整理過的日以
    `memory_consolidations` 標記跳過，✅ 庚-13／A-19）。

    ⚠️ 為什麼重試放在這一層而不是 `llm.py`（2026-07-27 實測）：`logs/scheduler.log` 的
    15 筆 RESOURCE_EXHAUSTED 全出在 daily-consolidation，路徑是
    fanout → consolidation → `mem0.add` → Gemini embedder——**完全不經過 `llm.py`**。
    在 LLM 層加重試一筆都攔不到；能同時涵蓋各種底層 seam 的位置只有這裡。

    `cron` 由 `cron/registry.py` 給定，本函式不自己算時刻——排程何時跑是全系統
    唯一一份的宣告（2026-07-27），散在各工廠會讓後台看到的與實際跑的不是同一件事。
    """

    # 每一筆處理＝一條 Opik root trace（工程觀測，OPIK_ENABLED 才生效）。內層 flow
    # （proactive_turn／nightly_reflection 等）本來各自是無根 trace，掛進本 root 後
    # 自然收斂為子 span；純提醒 job（用藥／回診，無 LLM）也因此首次可觀測。
    # 停用時 @track 退化為直呼 action，run() 的逐筆隔離語意一字不差。
    @tracing.track(name=name, type="general", capture_input=False, capture_output=False)
    def run_item(item: T) -> None:
        tracing.update_trace_metadata(job=name, item=item_id(item))
        action(item)

    def _run_with_retry(item: T) -> None:
        """逐筆執行；配額／限流錯誤有界退避重試，其餘立即上拋給外層的逐筆隔離。"""
        for attempt in range(1, max(1, retry_quota_attempts) + 1):
            try:
                run_item(item)
                return
            except Exception as exc:  # noqa: BLE001 - 由外層逐筆隔離接手
                last_attempt = attempt >= max(1, retry_quota_attempts)
                if last_attempt or not is_retryable_llm_error(exc):
                    raise
                delay = min(
                    _RETRY_BASE_BACKOFF_SECONDS * 2 ** (attempt - 1), _RETRY_MAX_BACKOFF_SECONDS
                )
                logger.warning(
                    "job %s 遇到配額限制，%.0f 秒後重試（第 %d／%d 次）：%s",
                    name,
                    delay,
                    attempt,
                    retry_quota_attempts,
                    item_id(item),
                )
                sleep(delay)

    def run() -> None:
        for item in population():
            try:
                _run_with_retry(item)
            except Exception:  # noqa: BLE001 - 單一對象失敗不影響其他
                logger.exception("job %s 處理失敗：%s", name, item_id(item))

    return Job(name=name, cron=cron, run=run, max_lateness_seconds=max_lateness_seconds)
