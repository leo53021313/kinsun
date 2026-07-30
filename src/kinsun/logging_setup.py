"""日誌設定的唯一入口。兩個常駐行程（web、排程 worker）啟動時各呼叫一次。

為什麼需要這個模組（2026-07-27 實測）：全庫原本只有 `scheduler/worker.py::main` 有一行
`logging.basicConfig`，**webhook 主行程完全沒有任何日誌設定**。實測 `logs/webhook.log`
裡只有 uvicorn 自己印的那幾行，39 個 `kinsun.*` logger 的 INFO 一行都不存在，
WARNING 以上走 `logging.lastResort`（stderr、無時間戳、無 logger 名）——出事時
「行程當時在做什麼、什麼時候開始壞的」這一格是空的。`scheduler/worker.py:112-114`
記載的「每晚反思靜默失敗六天沒人發現」就是這個缺口的代價。

刻意不做的事（都是實測過的取捨）：
- **不自己寫檔**。`scripts/kinsun.sh` 與 `deploy/kinsun-scheduler.service` 目前以 shell
  重導向接管 stdout/stderr；Python 端再開同一個路徑會變成兩方同時寫一個檔。要改成
  Python 接管，必須連同部署腳本與 systemd unit 一起改，屬部署面連動變更，不併在這裡。
  輪替（RotatingFileHandler）與 errors 分檔同理，等寫檔權責收回來再說。
- **不加 LOG_LEVEL 環境變數**。目前兩個呼叫端都用預設 INFO，與改動前的 worker 一致，
  沒有人需要調；`level` 開成參數已足夠。真的需要在正式環境調的那天再升格成設定鍵。
- **不動 uvicorn 的 handler**。它自有一套且運作正常（`logs/webhook.log` 的 `INFO:` 那些
  行就是它印的），接管只會把它的存取日誌格式一併弄壞。
"""

from __future__ import annotations

import contextvars
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

# 每行帶本輪的 kinsun trace_id（2026-07-27）。
#
# 政策：**logs 只記「什麼時候、發生了什麼事」，長輩的對話內容一律去 Opik 看**（Leo 定案）。
# 拿掉內容之後，「出站冒名防線攔截」這種訊息就沒有下文了——trace_id 是那道橋：
# 看到哪一輪出事，拿這個 id 去 Opik 查它到底講了什麼。
#
# 沒有 trace_id 的情境（排程 job、啟動階段、CLI）印 `-`，不可讓整行炸掉或消失。
_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("kinsun_log_trace_id", default="")
_NO_TRACE = "-"

# 格式沿用原 `worker.py::main` 的 basicConfig 再加一格 trace_id——排程日誌的既有形狀
# 幾乎不變，既有的 grep 與 `scripts/kinsun.sh` 查看習慣照舊可用。
_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(trace_id)s] %(message)s"


@contextmanager
def log_trace(trace_id: str) -> Iterator[None]:
    """在範圍內把 trace_id 蓋到每一行 log 上。由對話管線在每輪開頭呼叫。

    ⚠️ **載體必須是 contextvars，不可用 threading.local**：兩個入站 handler 都是
    `async def`（`channels/line/webhook.py`、`channels/app/turns.py`），同一條事件迴圈
    執行緒會交錯處理多位長輩的回合。threading.local 會把 A 長輩的 trace_id 貼到 B 長輩
    的 log 上——那比沒有 trace_id 更糟，因為它看起來是對的。
    `test_trace_id_does_not_leak_between_concurrent_turns` 用真的 asyncio 交錯守住這件事。

    附帶好處：`background.run` 與 `PreparedTurn` 都以 `contextvars.copy_context()` 起
    背景執行緒，trace_id 自動跟著過去，不必逐處傳遞。
    """
    token = _TRACE_ID.set(trace_id)
    try:
        yield
    finally:
        _TRACE_ID.reset(token)


def _install_trace_id_factory() -> None:
    """讓每一筆 LogRecord 都帶 `trace_id` 屬性。

    用 `setLogRecordFactory` 而非 handler 的 Filter：factory 對行程內**每一筆** record
    都生效，含 uvicorn 與第三方 logger；Filter 只掛在我們自己加的 handler 上，
    別人的 handler 印出來的行就會少那一格、格式對不齊。
    """
    global _previous_factory
    _previous_factory = logging.getLogRecordFactory()
    previous = _previous_factory

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.trace_id = _TRACE_ID.get() or _NO_TRACE
        return record

    logging.setLogRecordFactory(factory)


# 壓到 WARNING 的第三方 logger。依實測資料挑選，不憑印象擴充：
# `logs/scheduler.log` 1,744 行裡 httpx 佔 422 行（24%），全部是 Opik 每 10 秒一次的
# 存活探測與 span 批次上傳。httpcore 是 httpx 的傳輸層（同源噪音），opik 為其客戶端。
# ⚠️ 壓的是等級不是 logger：它們真的出事（WARNING／ERROR）仍然看得到。
NOISY_LOGGERS = ("httpx", "httpcore", "opik")

_configured = False
_previous_factory = None


def setup_logging(*, level: int = logging.INFO, stream: TextIO | None = None) -> None:
    """設定 root logger。重複呼叫是 no-op（`--reload` 與測試都會走到）。

    `stream` 預設 stderr——部署層以 shell 重導向把它接到 `logs/*.log`，見模組 docstring。
    """
    global _configured
    if _configured:
        return
    _install_trace_id_factory()
    handler = logging.StreamHandler(sys.stderr if stream is None else stream)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    _configured = True


def reset_for_test() -> None:
    """測試用：清回未設定狀態（不動 root 既有的 handler，由呼叫端自行還原）。

    LogRecord factory 必須一併還原——它是行程級的全域狀態，留著會讓後續測試的
    record 都多一個 trace_id 屬性。
    """
    global _configured, _previous_factory
    _configured = False
    if _previous_factory is not None:
        logging.setLogRecordFactory(_previous_factory)
        _previous_factory = None
