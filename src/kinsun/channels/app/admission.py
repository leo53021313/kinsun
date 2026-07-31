"""對講機的容量閘門（spec 2026-07-30 §10 B2）。

⚠️ 這**不是節流，是容量管理**。ASR 與 TTS 跑在同一顆 GPU 上，二十個人同時按下去
不會併行、只會在推論服務前排隊——結果是每個人都等到天荒地老。限制同時進行的輪數
並誠實告知排隊位置，等於「少數人順暢」勝過「所有人都卡」。

⚠️ **與 `ws.py` 既有的 `_InFlight` 是兩件不同的事**：後者限的是**單一連線**最多三輪
併發（同一位長輩連按太多次），這裡限的是**全體**同時佔用 GPU 的輪數。兩者並存。

⚠️ **進程內計數，是「每個 worker 各自」的上限，不是全域上限。**
後端正式模式跑多個 worker（`scripts/kinsun.sh` 的 `--workers "${WEB_WORKERS:-2}"`，
預設 2；見 `ws.py` 模組 docstring「後端正式模式跑兩個 worker」）。`limit=N` 只擋得住
**同一個** worker process 內的併發，實際全域同時佔用 GPU 的輪數上限是
`WEB_WORKERS × N`——只有 `KINSUN_RELOAD=1` 的開發模式才是單一 uvicorn 進程、這時
`N` 才等於全域上限。設定併發上限時務必連同 worker 數一起換算，否則「以為設 4，結果
GPU 同時被打 8 輪」正是這個閘門存在的理由失守。與 `web/ratelimit.py` 的
`SlidingWindowRateLimiter` 是同一種前提（單進程記憶體實作，多 worker 下各進程獨立
計數，實際上限＝設定值×worker 數）。**不要**為此改成跨進程共享狀態（如 Postgres
advisory lock）——畢典場景是單機單張 GPU、worker 數量小且固定，換共享狀態是過度
工程；真的要撐多機部署才需要重新評估。
"""

from __future__ import annotations

import itertools
import threading
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class AdmissionTimeout(Exception):
    """排隊超過上限仍未輪到。呼叫端應回一句人話，不可靜默丟掉這一輪。"""


class TurnAdmission:
    """先到先服務的容量閘門：滿了要排隊，且**先排隊的人保證先拿到**（FIFO 取號）。

    ⚠️ `admit()` 是 context manager 工廠，取得的物件必須配 `with` 使用；若忘了寫
    `with gate.admit():` 而只是呼叫 `gate.admit()`，產生器本體完全不會執行——
    不佔名額、不排隊、不會報錯，靜默地什麼事都沒發生，呼叫端會以為自己已經卡了位。
    """

    def __init__(self, limit: int, *, queue_timeout: float = 30.0) -> None:
        if limit < 1:
            raise ValueError("併發上限至少要是 1")
        if queue_timeout is None or queue_timeout <= 0:
            raise ValueError(
                "queue_timeout 必須是大於 0 的秒數："
                "None 會讓排隊永久等待，<=0 會讓排隊形同不排隊（靜默失去容量保護）"
            )
        self._limit = limit
        self._queue_timeout = queue_timeout
        self._active = 0
        self._cond = threading.Condition()
        # 佇列存的是「取號序」，不是佔位；先到先得的順序完全由這個序決定，
        # 不依賴 threading.Condition 內部喚醒順序（那個順序不保證公平）。
        self._queue: deque[int] = deque()
        self._next_ticket = itertools.count(1)

    def active(self) -> int:
        with self._cond:
            return self._active

    def waiting(self) -> int:
        with self._cond:
            return len(self._queue)

    @contextmanager
    def admit(self, *, on_queued: Callable[[int], None] | None = None) -> Iterator[None]:
        """取得一個名額；滿了就排隊取號，並以 `on_queued(位置)` 回報。

        ⚠️ **佇列先到先得，名額夠也不可插隊**：只有「有空位**且**佇列是空的」才走
        快速通道直接放行；佇列非空時，即使當下有空位也要乖乖排到隊尾，等前面的人
        都輪過一次。少了「佇列是空的」這個條件，晚到的人會在名額釋放的瞬間直接搶
        走，讓已經排隊的人平白多等一輪——`on_queued` 回報的位置就形同虛設的謊言。

        ⚠️ `on_queued` 在**沒有持鎖**時呼叫（取號、算好位置之後才呼叫，見下方實作）：
        它的用途是把一則訊框丟進送出佇列，即使呼叫端做的是會阻塞的 I/O（例如
        `ws.py` 的 `_Sender.send` 走 `future.result(timeout=5)`、最長等 5 秒），
        也只會拖到呼叫者自己這一輪，不會拖住整個閘門——若改回持鎖時呼叫，一位
        WebSocket 訊號不穩的長輩就能讓所有人的 `admit()`／`active()`／`waiting()`
        一起被鎖住長達 5 秒。

        ⚠️ 名額的釋放放在 finally。漏放一次那個名額就永久消失，漏放到滿之後
        所有人從此都在排隊，而伺服器看起來完全健康——那是最難查的一種故障。
        """
        position: int | None = None
        my_ticket: int | None = None
        with self._cond:
            if self._active < self._limit and not self._queue:
                self._active += 1
            else:
                my_ticket = next(self._next_ticket)
                self._queue.append(my_ticket)
                position = len(self._queue)

        if my_ticket is not None:
            if on_queued is not None:
                on_queued(position)
            with self._cond:
                try:
                    granted = self._cond.wait_for(
                        lambda: (
                            self._active < self._limit
                            and bool(self._queue)
                            and self._queue[0] == my_ticket
                        ),
                        timeout=self._queue_timeout,
                    )
                finally:
                    # ⚠️ 不管有沒有輪到，都要把自己的號碼從佇列拿掉：逾時的人若
                    # 還留在佇列裡，後面的人看到的位置會越報越誇張、而前面根本
                    # 沒有人；輪到的人也要拿掉——佇列只記排隊順序，不是進場憑證。
                    if my_ticket in self._queue:
                        self._queue.remove(my_ticket)
                if not granted:
                    raise AdmissionTimeout
                self._active += 1
        try:
            yield
        finally:
            with self._cond:
                self._active -= 1
                # notify_all 而非只 notify 一位：FIFO 順序由號碼、不是由誰先被
                # 喚醒決定——被叫醒但還沒輪到號的人會在 wait_for 的述詞裡發現
                # 不是自己，重新睡回去，不會因為被叫錯而讓真正該輪到的人多等。
                self._cond.notify_all()
