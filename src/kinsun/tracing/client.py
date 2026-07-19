"""Opik 設定與全域開關；唯一決定 is_enabled() 的地方。"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("kinsun.tracing")

_ENABLED = False


def configure(settings) -> None:
    """依設定啟用/停用 Opik。停用或未安裝 opik 套件時，is_enabled() 恆 False。

    只設環境變數與旗標，不建立連線（連線由 opik SDK 首次送 trace 時自建）。
    以 setdefault 讓真實環境變數優先（與 config.load_dotenv 一致）。
    """
    global _ENABLED
    if not settings.opik_enabled:
        _ENABLED = False
        return
    try:
        import opik  # noqa: F401  只確認可匯入
    except ImportError:
        logger.warning("OPIK_ENABLED=true 但未安裝 opik 套件；工程觀測停用。")
        _ENABLED = False
        return
    os.environ.setdefault("OPIK_URL_OVERRIDE", settings.opik_url_override)
    os.environ.setdefault("OPIK_WORKSPACE", settings.opik_workspace)
    os.environ.setdefault("OPIK_PROJECT_NAME", settings.opik_project_name)
    _ENABLED = True
    logger.info("Opik 工程觀測已啟用：%s", settings.opik_url_override)


def is_enabled() -> bool:
    return _ENABLED


def reset_for_test() -> None:
    """測試用：清回未設定狀態。"""
    global _ENABLED
    _ENABLED = False
