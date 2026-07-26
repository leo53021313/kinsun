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

import logging
import sys
from typing import TextIO

# 格式與原 `worker.py::main` 的 basicConfig 逐字相同——排程日誌的既有形狀不因本次改動而變，
# 既有的 grep 與 `scripts/kinsun.sh` 的查看習慣照舊可用。
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

# 壓到 WARNING 的第三方 logger。依實測資料挑選，不憑印象擴充：
# `logs/scheduler.log` 1,744 行裡 httpx 佔 422 行（24%），全部是 Opik 每 10 秒一次的
# 存活探測與 span 批次上傳。httpcore 是 httpx 的傳輸層（同源噪音），opik 為其客戶端。
# ⚠️ 壓的是等級不是 logger：它們真的出事（WARNING／ERROR）仍然看得到。
NOISY_LOGGERS = ("httpx", "httpcore", "opik")

_configured = False


def setup_logging(*, level: int = logging.INFO, stream: TextIO | None = None) -> None:
    """設定 root logger。重複呼叫是 no-op（`--reload` 與測試都會走到）。

    `stream` 預設 stderr——部署層以 shell 重導向把它接到 `logs/*.log`，見模組 docstring。
    """
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stderr if stream is None else stream)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level)
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    _configured = True


def reset_for_test() -> None:
    """測試用：清回未設定狀態（不動 root 既有的 handler，由呼叫端自行還原）。"""
    global _configured
    _configured = False
