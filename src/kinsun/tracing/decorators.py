"""track 裝飾器與 trace 標記；停用時全部 no-op。"""

from __future__ import annotations

import functools
import logging

from kinsun.tracing.client import is_enabled

logger = logging.getLogger("kinsun.tracing")


def track(name=None, type="general", capture_input=True, capture_output=True):
    """為函式加 Opik span。開關判斷延後到呼叫時（裝飾器在 import 期套用，早於 configure）。

    停用＝直接跑原函式；啟用＝首次呼叫時才 lazy 包成 opik.track 並快取。
    """

    def decorator(func):
        opik_wrapped = None

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal opik_wrapped
            if not is_enabled():
                return func(*args, **kwargs)
            if opik_wrapped is None:
                from opik import track as opik_track

                opik_wrapped = opik_track(
                    name=name,
                    type=type,
                    capture_input=capture_input,
                    capture_output=capture_output,
                )(func)
            return opik_wrapped(*args, **kwargs)

        return wrapper

    return decorator


def tag_current_trace(*, trace_id="", channel="", elder_id="", **extra) -> None:
    """把 kinsun 的 trace_id 掛到當前 Opik trace（metadata + tags + thread），供 UI 關聯與搜尋。

    - elder_id 非空時設為 thread_id：同一長輩的多回合在 Opik 串成一條對話串（E1）。
    - **extra 追加任意 metadata（如 model、tier）。
    觀測失敗不可中斷對話：任何例外都吞掉並記 warning。停用時 no-op。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        metadata = {"kinsun_trace_id": trace_id, "elder_id": elder_id, **extra}
        kwargs = {"metadata": metadata, "tags": [t for t in (channel,) if t]}
        if elder_id:
            kwargs["thread_id"] = elder_id
        opik_context.update_current_trace(**kwargs)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik trace 標記失敗 trace=%s", trace_id)


def update_trace_metadata(**fields) -> None:
    """對當前 trace 追加 metadata（如風險 tier、是否走 fallback）；停用/失敗 no-op。

    用於 root 之後才算出的欄位——root 埋點時 tier/fallback 尚未知。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        opik_context.update_current_trace(metadata=fields)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik trace metadata 更新失敗")


def log_feedback_score(name, value, *, reason="") -> None:
    """對當前 trace 掛回饋分數（家屬/長輩評分、線上評測規則）；停用/失敗 no-op。"""
    if not is_enabled():
        return
    try:
        from opik import opik_context

        opik_context.update_current_trace(
            feedback_scores=[{"name": name, "value": value, "reason": reason}]
        )
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik feedback 掛載失敗 name=%s", name)


def set_current_trace_io(*, user_input: str = "", assistant_output: str = "") -> None:
    """把該輪的長輩原話與金孫回覆寫進當前 trace 的 input/output，讓 Opik Threads
    視圖顯示實際對話（First／Last message）；停用/失敗 no-op。

    刻意獨立於 @track 的 capture_input/output——那會連 audio bytes 與內部物件一起吞；
    這裡只寫乾淨文字。空字串者略過（如靜音誤觸沒有可顯示的原話）。update_current_trace
    對 input/output 是合併寫入、對 None 略過，故與既有的 metadata/thread 標記互不覆蓋。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        payload: dict = {}
        if user_input:
            payload["input"] = {"text": user_input}
        if assistant_output:
            payload["output"] = {"text": assistant_output}
        if payload:
            opik_context.update_current_trace(**payload)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik trace I/O 寫入失敗")


def set_current_span_io(*, span_input=None, span_output=None) -> None:
    """把乾淨內容寫進當前 span（非 trace）的 input/output；停用/失敗 no-op。

    用於巢狀在 root 下的子流程（記憶寫入／每日摘要／每晚反思）——這些函式的參數多為
    store/client 物件（含 self），不能用 @track 的 capture_input/output（會吞內部物件、
    甚至 api_key／連線池），故在算出乾淨文字的點明確寫入本層 span。None 者略過。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        payload: dict = {}
        if span_input is not None:
            payload["input"] = span_input
        if span_output is not None:
            payload["output"] = span_output
        if payload:
            opik_context.update_current_span(**payload)
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik span I/O 寫入失敗")
