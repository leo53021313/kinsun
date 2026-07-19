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


def tag_current_trace(*, trace_id, channel="", elder_id="") -> None:
    """把 kinsun 的 trace_id 掛到當前 Opik trace（metadata + tags），供 UI 關聯與搜尋。

    觀測失敗不可中斷對話：任何例外都吞掉並記 warning。停用時 no-op。
    """
    if not is_enabled():
        return
    try:
        from opik import opik_context

        opik_context.update_current_trace(
            metadata={"kinsun_trace_id": trace_id, "elder_id": elder_id},
            tags=[t for t in (channel,) if t],
        )
    except Exception:  # noqa: BLE001 - 觀測失敗絕不中斷對話
        logger.warning("Opik trace 標記失敗 trace=%s", trace_id)
