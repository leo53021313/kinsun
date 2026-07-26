"""排程狀態持久化：每個 job 的 last_run。Protocol + Postgres 實作。"""

from __future__ import annotations

from datetime import datetime, tzinfo
from typing import Protocol

from kinsun.db import Database, _Errors


class ScheduleStateError(Exception):
    """排程狀態讀寫失敗。"""


# 認領條件的容差（秒）。**絕對不可**改回浮點等值比對——見 try_claim docstring。
# 取 1 毫秒：遠大於任何浮點文字往返的誤差（微秒等級），也遠小於最密的 cron 間隔（1 分鐘），
# 兩端都留了三個數量級的餘裕。
CLAIM_TOLERANCE_SECONDS = 0.001


class ScheduleStateStore(Protocol):
    def get_last_run(self, job_name: str) -> datetime | None: ...
    def set_last_run(self, job_name: str, when: datetime) -> None: ...
    def try_claim(self, job_name: str, *, expected: datetime, now: datetime) -> bool: ...


class PgScheduleStateStore:
    """排程狀態的 Postgres（Supabase）實作；介面同 ScheduleStateStore。"""

    def __init__(self, db: Database, tz: tzinfo) -> None:
        self._db = _Errors(db, lambda m: ScheduleStateError(f"排程狀態存取失敗：{m}"))
        self._tz = tz

    def get_last_run(self, job_name: str) -> datetime | None:
        row = self._db.query_one(
            "SELECT last_run_at FROM scheduler_state WHERE job_name = %s",
            (job_name,),
        )
        if row is None or row[0] is None:
            return None
        return datetime.fromtimestamp(row[0], self._tz)

    def set_last_run(self, job_name: str, when: datetime) -> None:
        self._db.execute(
            "INSERT INTO scheduler_state (job_name, last_run_at) VALUES (%s, %s) "
            "ON CONFLICT (job_name) DO UPDATE SET last_run_at = EXCLUDED.last_run_at",
            (job_name, when.timestamp()),
        )

    def try_claim(self, job_name: str, *, expected: datetime, now: datetime) -> bool:
        """原子先搶先贏（✅ 庚-17／A-42）：現值未超過我讀到的 expected 才更新成 now。

        誤起雙 worker 時，兩邊都判定到期、拿同一個 expected 來搶——條件式
        UPDATE 保證只有一個成功（贏家把 last_run_at 推到 now，遠大於 expected＋容差，
        輸家的條件因此不成立），輸家跳過該 job，長輩不會收到雙重提醒。

        ## ⚠️ 為什麼是 `<=` 加容差，而不是 `=`（2026-07-26 正式環境停擺事故）

        原本寫 `WHERE last_run_at = %s`，註解寫著「epoch 秒往返無精度損失，等值比較安全」。
        **那句話是錯的**，而且讓整個排程器靜默停擺：

        Supabase 這條連線的 `extra_float_digits = 0`，PostgreSQL 於是只用 **15 位有效數字**
        輸出 `double precision`。實際儲存的 `1785045932.084225` 送到用戶端變成
        `1785045932.08422`——**是另一個 double**。於是：

        1. `get_last_run` 讀回被截斷的值
        2. `try_claim` 拿它去 `WHERE last_run_at = %s`，永遠對不上
        3. 該 job **從此再也認領不到，直到有人手動改資料庫**

        當天現場：`schedule-dispatch` 卡在 14:05、`daily-consolidation` 卡在 13.8 天前，
        排程器本身活得好好的、每分鐘照掃，`kinsun.sh status` 顯示 RUNNING——因為它真的
        在跑，只是每一輪都認領失敗。重啟六次沒有用：壞掉的值在資料庫裡，不在記憶體裡。
        每個 job 各自卡在「它的時間戳剛好需要 16 位以上有效數字」的那一刻，所以是隨機、
        逐一、無聲地死去。

        修法刻意**不賭連線設定**（`extra_float_digits` 由 Supabase 端決定，我們改不到，
        而且 `options=-c ...` 經連線池不生效，見 db.py 的註解）：改成範圍比對，讓
        亞毫秒級的文字往返誤差再也影響不了正確性。全庫其他浮點比對本來就都是
        `>=`／`<=` 範圍式，只有這裡用等值——這是它唯一的受害點。
        """
        rows = self._db.query(
            "UPDATE scheduler_state SET last_run_at = %s "
            "WHERE job_name = %s AND last_run_at <= %s RETURNING job_name",
            (now.timestamp(), job_name, expected.timestamp() + CLAIM_TOLERANCE_SECONDS),
        )
        return bool(rows)


class FakeScheduleStateStore:
    """ScheduleStateStore 的記憶體替身（測試用，不碰 DB）。

    與 PgScheduleStateStore 的差異：Pg 以 epoch 秒（DOUBLE PRECISION）存讀，
    get_last_run 會用建構時的 tz 重建 datetime；本替身則原樣保存傳入的 datetime。
    對「時間點」（`.timestamp()`／aware datetime 的 `==`）兩者一致，故合約測試以
    `.timestamp()` 比較。無 tz 參數的替身無法在此處複製 Pg 的 tz 正規化，也不需要。
    """

    def __init__(self) -> None:
        self._last: dict[str, datetime] = {}

    def get_last_run(self, job_name: str) -> datetime | None:
        return self._last.get(job_name)

    def set_last_run(self, job_name: str, when: datetime) -> None:
        self._last[job_name] = when

    def try_claim(self, job_name: str, *, expected: datetime, now: datetime) -> bool:
        # 與 Pg 同語意：現值未超過 expected＋容差才搶得到（見 PgScheduleStateStore.try_claim
        # 對 2026-07-26 停擺事故的說明）。替身不會有浮點截斷，但合約必須一致，
        # 否則測試綠燈、正式環境照樣停擺——這次就是這樣漏掉的。
        current = self._last.get(job_name)
        if current is None or current.timestamp() > expected.timestamp() + CLAIM_TOLERANCE_SECONDS:
            return False
        self._last[job_name] = now
        return True
