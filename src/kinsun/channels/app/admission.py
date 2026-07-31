"""對講機的容量閘門（spec 2026-07-30 §10 B2）。

⚠️ 這**不是節流，是容量管理**。ASR 與 TTS 跑在同一顆 GPU 上，二十個人同時按下去
不會併行、只會在推論服務前排隊——結果是每個人都等到天荒地老。限制同時進行的輪數
並誠實告知排隊位置，等於「少數人順暢」勝過「所有人都卡」。

⚠️ **與 `ws.py` 既有的 `_InFlight` 是兩件不同的事**：後者限的是**單一連線**最多三輪
併發（同一位長輩連按太多次），這裡限的是**全體**同時佔用 GPU 的輪數。兩者並存。

⚠️ 進程內計數。後端目前跑單一 worker（`kinsun.sh` 的 uvicorn 未指定 `--workers`），
所以這樣就是全域上限。**若日後開多 worker，這個閘門會退化成「每個 worker 各 N 輪」**
——屆時要改用共享狀態（如 Postgres 的 advisory lock），不要以為它還在保護 GPU。
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class AdmissionTimeout(Exception):
    """排隊超過上限仍未輪到。呼叫端應回一句人話，不可靜默丟掉這一輪。"""


class TurnAdmission:
    def __init__(self, limit: int, *, queue_timeout: float = 30.0) -> None:
        if limit < 1:
            raise ValueError("併發上限至少要是 1")
        self._limit = limit
        self._queue_timeout = queue_timeout
        self._active = 0
        self._waiting = 0
        self._cond = threading.Condition()

    def active(self) -> int:
        with self._cond:
            return self._active

    def waiting(self) -> int:
        with self._cond:
            return self._waiting

    @contextmanager
    def admit(self, *, on_queued: Callable[[int], None] | None = None) -> Iterator[None]:
        """取得一個名額；滿了就排隊，並以 `on_queued(位置)` 回報。

        ⚠️ `on_queued` 在持有鎖時呼叫，**必須是非阻塞的**——它的用途是把一則訊框
        丟進送出佇列，不可以在裡面做 I/O。會阻塞的話，整個閘門會跟著卡死。

        ⚠️ 名額的釋放放在 finally。漏放一次那個名額就永久消失，漏放到滿之後
        所有人從此都在排隊，而伺服器看起來完全健康——那是最難查的一種故障。
        """
        with self._cond:
            if self._active >= self._limit:
                self._waiting += 1
                if on_queued is not None:
                    on_queued(self._waiting)
                try:
                    granted = self._cond.wait_for(
                        lambda: self._active < self._limit, timeout=self._queue_timeout
                    )
                finally:
                    # ⚠️ 一定要在 finally 減回去：逾時的人若還算在排隊人數裡，
                    # 後面的人看到的位置會越報越誇張，而實際上前面根本沒有人。
                    self._waiting -= 1
                if not granted:
                    raise AdmissionTimeout
            self._active += 1
        try:
            yield
        finally:
            with self._cond:
                self._active -= 1
                self._cond.notify()
