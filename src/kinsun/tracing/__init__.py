"""工程觀測（Opik）整合：唯一 import opik 之處，其餘程式只依賴本套件的薄封裝。

比照 rag/vector_store.py 的外部服務 adapter 定位（免三件套）。以 OPIK_ENABLED
全域開關——關閉時所有裝飾器/包裝退化為 no-op，對主流程零影響。
"""

from __future__ import annotations

from kinsun.tracing.client import configure, is_enabled
from kinsun.tracing.decorators import tag_current_trace, track

__all__ = ["configure", "is_enabled", "tag_current_trace", "track"]
