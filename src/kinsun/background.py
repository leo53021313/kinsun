"""背景落庫：把「沒有任何後續步驟在等」的寫入移出長輩的回覆路徑。

為什麼需要這個模組（2026-07-26 延遲實測）：Supabase 是跨網服務，實測單次往返固定
約 0.21 秒且與查詢複雜度無關，而一輪對話要打 15 次——約 4.5 秒、佔端到端延遲
四分之一以上，純粹是網路往返在排隊。其中 6 次（5 筆觀測稽核 ＋ 1 筆提醒回應標記）
沒有任何後續步驟會讀它們，卻整整擋在長輩聽到回覆之前。

契約與 `tracing` 同構（本專案既有慣例）：預設**同步**——未 `configure()` 時
`run()` 就地執行，單元測試與 CLI 一字不差維持原行為；由組裝根（app.py）啟用。

刻意不做的事：
- 不重試。這些寫入本來就是 best-effort（`observability.store.safe_record` 一向
  吞掉錯誤只留 warning），為它們加重試等於為了稽核資料去賭主流程的資源。
- 佇列不是無上限的。Supabase 慢下來時，無上限佇列會把行程的記憶體吃光，連帶
  弄死長輩的對話——那比少幾筆稽核嚴重得多，故過載時丟棄並留警告。
"""

from __future__ import annotations

import contextvars
import logging
import queue
import threading
from collections.abc import Callable

logger = logging.getLogger("kinsun.background")

# 佇列上限：一輪對話產生 6 筆背景寫入，256 約等於 40 輪的積壓。會積到這個量，
# 代表資料庫已經慢到主流程也早就出事了，此時保住行程比保住稽核重要。
_DEFAULT_MAX_PENDING = 256


class _Writer:
    """單純的有界工作佇列。獨立成類別是為了讓 configure() 能整個換掉舊的池。"""

    def __init__(self, *, max_workers: int, max_pending: int) -> None:
        self._queue: queue.Queue[Callable[[], None] | None] = queue.Queue(maxsize=max_pending)
        self._threads = [
            threading.Thread(target=self._loop, name=f"kinsun-bg-{i}", daemon=True)
            for i in range(max_workers)
        ]
        self.is_closed = False
        for thread in self._threads:
            thread.start()

    def submit(self, action: Callable[[], None]) -> None:
        try:
            self._queue.put_nowait(action)
        except queue.Full:
            logger.warning("背景落庫佇列已滿，丟棄本筆寫入")

    def _loop(self) -> None:
        while True:
            action = self._queue.get()
            try:
                if action is None:  # 收工訊號
                    return
                action()
            except Exception:  # noqa: BLE001 - 背景例外沒有呼叫端可接，就地吞掉
                logger.warning("背景落庫失敗", exc_info=True)
            finally:
                self._queue.task_done()

    def close(self) -> None:
        """排空已排隊的寫入後收工——部署重啟不該吃掉最後幾筆觀測。"""
        if self.is_closed:
            return
        self.is_closed = True
        self._queue.join()
        for _ in self._threads:
            self._queue.put(None)
        for thread in self._threads:
            thread.join(timeout=5)


_writer: _Writer | None = None


def configure(*, max_workers: int = 2, max_pending: int = _DEFAULT_MAX_PENDING) -> None:
    """啟用背景落庫。重複呼叫會先關掉舊的池（--reload 開發模式會走到）。

    `max_workers` 預設 2 而非更多：背景寫入與前景查詢共用同一個 psycopg 連線池
    （`DATABASE_POOL_MAX_SIZE`，預設 5），開太多執行緒只會讓前景查詢等連線，
    把省下來的時間又還回去。
    """
    global _writer
    if _writer is not None:
        _writer.close()
    _writer = _Writer(max_workers=max_workers, max_pending=max_pending)
    logger.info("背景落庫已啟用：%d 個 worker、佇列上限 %d", max_workers, max_pending)


class Handle:
    """一筆背景工作的完成訊號。

    大多數呼叫端不理它（觀測稽核沒有人在等）。少數呼叫端有一條**後續步驟真的會讀
    這筆寫入**的路徑，需要在交出回應前收斂——見 `agent._record_turn_background`
    與 `pipeline._process_transcribed`（2026-07-30 審查 H2）。

    `wait` 回傳「這筆到底做完了沒有」，而不是無條件放行：呼叫端據此決定要不要留
    warning，讓「背景寫入落後」變成看得見的事實。
    """

    def __init__(self, *, done: bool = False) -> None:
        self._event = threading.Event()
        if done:  # 同步模式（未 configure）：呼叫 run() 回來時就已經做完了
            self._event.set()

    def _mark_done(self) -> None:
        self._event.set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)


def run(action: Callable[[], None]) -> Handle:
    """把 action 丟到背景執行；未 configure 時就地執行（預設）。回傳完成訊號。

    以 `contextvars.copy_context()` 帶入呼叫端的 context，Opik 的 span 巢狀與
    `turn_context.elder_utterance` 在背景執行緒裡才不會憑空消失。

    ⚠️ 佇列滿時整筆被丟棄（見 `_Writer.submit`），此時 handle **永遠不會**變成
    done——這正是呼叫端該看到的事實，故刻意不在丟棄時把它標記完成。
    """
    writer = _writer
    if writer is None:
        action()
        return Handle(done=True)
    handle = Handle()
    context = contextvars.copy_context()

    def guarded() -> None:
        try:
            context.run(action)
        finally:
            handle._mark_done()

    writer.submit(guarded)
    return handle


def shutdown() -> None:
    """關閉背景落庫並排空佇列。⚠️ 必須在關閉資料庫連線池**之前**呼叫。"""
    global _writer
    if _writer is None:
        return
    _writer.close()
    _writer = None


def reset_for_test() -> None:
    """測試用：清回未設定（＝同步）狀態。"""
    shutdown()
