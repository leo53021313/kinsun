"""Opik 設定與全域開關；唯一決定 is_enabled() 的地方。"""

from __future__ import annotations

import logging
import os
import urllib.request

logger = logging.getLogger("kinsun.tracing")

_ENABLED = False


def _is_opik_reachable(url_override: str, timeout: float) -> bool:
    """探測自架 Opik 是否可達；連不到／逾時／任何網路錯誤都回 False（安靜降級）。

    抽成模組層函式是為了讓測試可 monkeypatch，不必真的起 Opik 服務。
    """
    ping_url = url_override.rstrip("/") + "/is-alive/ping"
    try:
        with urllib.request.urlopen(ping_url, timeout=timeout) as response:  # noqa: S310 - 固定內部位址
            return 200 <= response.status < 300
    except Exception:  # noqa: BLE001 - 連不到就是不可用，不區分錯誤型別
        return False


def configure(settings) -> None:
    """依設定啟用/停用 Opik。停用、未裝 opik 套件、或連不到服務時，is_enabled() 恆 False。

    只設環境變數與旗標，不建立長連線（trace 連線由 opik SDK 首次送出時自建）；
    但啟用時會先做一次輕量連線探測——OPIK_ENABLED 預設為 true，Windows/macOS 開發機或
    CI 常無 Opik 服務，先探測可避免整段流程被背景送 trace 的連線錯誤洗版。
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
    if not _is_opik_reachable(settings.opik_url_override, settings.opik_ping_timeout_seconds):
        logger.warning(
            "OPIK_ENABLED=true 但連不到 Opik 服務（%s）；工程觀測停用，不影響主流程。",
            settings.opik_url_override,
        )
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
