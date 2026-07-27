"""Opik 設定與全域開關；唯一決定 is_enabled() 的地方。"""

from __future__ import annotations

import logging
import os
import time
import urllib.request

logger = logging.getLogger("kinsun.tracing")

_ENABLED = False
# 探測失敗後允許重探的設定；None＝不再重探（未 configure、開關關閉、或未裝 opik 套件）。
_SETTINGS = None
# 下次可重探的單調時刻（僅在 _ENABLED 為 False 且 _SETTINGS 非 None 時有意義）。
_NEXT_PROBE_AT = 0.0


def _now() -> float:
    """單調時鐘；抽成模組層函式是為了讓測試可 monkeypatch，不必真的等一個重探間隔。"""
    return time.monotonic()


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


def _probe_and_enable() -> bool:
    """探測一次：可達就啟用並匯出 SDK 需要的環境變數，否則排定下次可重探的時刻。

    ⚠️ 環境變數必須跟著「啟用」一起設——opik SDK 靠它們決定送去哪個後端／工作區／
    專案，漏設就會退回 SDK 預設（雲端），所以重探成功這條路徑也得走同一段，不能
    只翻旗標。以 setdefault 讓真實環境變數優先（與 config.load_dotenv 一致）。
    """
    global _ENABLED, _NEXT_PROBE_AT
    settings = _SETTINGS
    if settings is None:
        return False
    if not _is_opik_reachable(settings.opik_url_override, settings.opik_ping_timeout_seconds):
        _NEXT_PROBE_AT = _now() + settings.opik_reprobe_interval_seconds
        return False
    os.environ.setdefault("OPIK_URL_OVERRIDE", settings.opik_url_override)
    os.environ.setdefault("OPIK_WORKSPACE", settings.opik_workspace)
    os.environ.setdefault("OPIK_PROJECT_NAME", settings.opik_project_name)
    _ENABLED = True
    logger.info("Opik 工程觀測已啟用：%s", settings.opik_url_override)
    return True


def configure(settings) -> None:
    """依設定啟用/停用 Opik。停用或未裝 opik 套件時，is_enabled() 恆 False。

    只設環境變數與旗標，不建立長連線（trace 連線由 opik SDK 首次送出時自建）；
    但會先做一次輕量連線探測——OPIK_ENABLED 預設為 true，Windows/macOS 開發機或
    CI 常無 Opik 服務，先探測可避免整段流程被背景送 trace 的連線錯誤洗版。

    ⚠️ 首探失敗**不是終身判決**，理由見 is_enabled() 的重探說明。
    """
    global _ENABLED, _SETTINGS
    _ENABLED = False
    _SETTINGS = None
    if not settings.opik_enabled:
        return
    try:
        import opik  # noqa: F401  只確認可匯入
    except ImportError:
        logger.warning("OPIK_ENABLED=true 但未安裝 opik 套件；工程觀測停用。")
        return
    # 開關開著且套件在＝使用者要觀測，故首探失敗仍允許重探（Opik 可能只是還沒起來）。
    _SETTINGS = settings
    if _probe_and_enable():
        return
    logger.warning(
        "OPIK_ENABLED=true 但目前連不到 Opik 服務（%s）；工程觀測暫時停用，"
        "每 %.0f 秒重探一次，服務起來後會自動接回，不影響主流程。",
        settings.opik_url_override,
        settings.opik_reprobe_interval_seconds,
    )


def is_enabled() -> bool:
    """工程觀測目前是否啟用；停用期間每隔一個重探間隔會實際探測一次。

    ⚠️ 為什麼要重探（2026-07-27 事故）：先前首探失敗就永久停用，而 kinsun.sh 全套
    restart 時 opik 第一個停、最後一個起（冷啟 30–60 秒），webhook 早在自己啟動後
    2 秒就探測完並放棄——於是那個行程整段壽命的長輩對話一筆都沒進 Opik，即使 Opik
    一分鐘後就活著。同一個洞也涵蓋「Opik 中途重啟」：那時沒人會去重啟 webhook，
    觀測就這樣一路啞掉，而且不會有任何人發現。

    成本：已啟用時直接回 True，零成本——這條路徑在對話熱路徑上每個 span 都會走到。
    只有停用期間才可能探測，且每個間隔至多一次（失敗即重新排定），最壞是每
    opik_reprobe_interval_seconds 多一次本機 ping；連不到時 localhost 是
    connection refused 立即返回（不到 1ms），只有「服務在但卡住」才會等滿
    opik_ping_timeout_seconds。

    多執行緒（uvicorn threadpool）下最壞情況是同時多探幾次，結果一致、無副作用，
    故不加鎖——為此加鎖等於讓熱路徑替一個無害的競態付代價。
    """
    if _ENABLED:
        return True
    if _SETTINGS is None or _now() < _NEXT_PROBE_AT:
        return False
    return _probe_and_enable()


def reset_for_test() -> None:
    """測試用：清回未設定狀態。"""
    global _ENABLED, _SETTINGS, _NEXT_PROBE_AT
    _ENABLED = False
    _SETTINGS = None
    _NEXT_PROBE_AT = 0.0
