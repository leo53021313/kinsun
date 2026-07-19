"""包 google-genai client，取得 LLM 呼叫的自動捕捉（輸入/輸出/token/模型參數）。"""

from __future__ import annotations

import logging

from kinsun.tracing.client import is_enabled

logger = logging.getLogger("kinsun.tracing")


def wrap_genai(client):
    """啟用時以 Opik 包裝 google-genai client；停用或包裝失敗則原樣回傳。"""
    if not is_enabled():
        return client
    try:
        from opik.integrations.genai import track_genai

        return track_genai(client)
    except Exception:  # noqa: BLE001 - 包裝失敗不可影響 LLM 可用性
        logger.warning("track_genai 包裝失敗；LLM 觀測略過。")
        return client
