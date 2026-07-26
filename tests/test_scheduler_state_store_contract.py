"""ScheduleStateStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的 job_name，才能在共用真庫上互不干擾。

注意：PgScheduleStateStore 以 epoch 秒存讀，get_last_run 會用建構時的 tz 重建
datetime；Fake 則原樣保存。兩者對「時間點」一致，故一律以 `.timestamp()` 比較。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from kinsun.scheduler.state import FakeScheduleStateStore, PgScheduleStateStore

TPE = timezone(timedelta(hours=8))


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgScheduleStateStore(request.getfixturevalue("pg_database"), ZoneInfo("Asia/Taipei"))
    return FakeScheduleStateStore()


def test_get_last_run_none_before_any_set(store, ns):
    assert store.get_last_run(f"{ns}a") is None


def test_set_then_get_round_trips_timestamp(store, ns):
    when = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)
    store.set_last_run(f"{ns}a", when)
    got = store.get_last_run(f"{ns}a")
    assert got is not None
    assert got.timestamp() == when.timestamp()


def test_per_job_name_isolation(store, ns):
    # 設定 job A 不應影響 job B。
    store.set_last_run(f"{ns}a", datetime(2026, 6, 29, 3, 0, tzinfo=TPE))
    assert store.get_last_run(f"{ns}b") is None


def test_try_claim_tolerates_a_truncated_expected_value(store, ns):
    """讀回值比實際儲存值少了幾位小數時，仍然必須認領得到。

    ⚠️ 這條守的是 2026-07-26 正式環境停擺事故：Supabase 連線的 `extra_float_digits = 0`
    讓 PostgreSQL 只用 15 位有效數字輸出 double，`1785045932.084225` 讀回來變成
    `1785045932.08422`（另一個 double）。舊的 `WHERE last_run_at = %s` 因此永遠對不上，
    每個 job 在「時間戳剛好需要 16 位以上」的那一刻無聲死掉，再也不會執行——
    排程器本身還活著、每分鐘照掃，狀態頁顯示 RUNNING，重啟六次也沒用（壞值在資料庫裡）。

    以「讀回值略小於實際值」模擬截斷；容差內就得認領成功。
    """
    seed = datetime(2026, 7, 12, 3, 0, 0, 84225, tzinfo=TPE)
    store.set_last_run(f"{ns}job", seed)
    truncated = seed - timedelta(microseconds=5)  # 讀回時掉了幾位小數
    now = datetime(2026, 7, 13, 3, 0, tzinfo=TPE)
    assert store.try_claim(f"{ns}job", expected=truncated, now=now) is True, (
        "亞微秒的往返誤差就讓 job 永遠認領不到——這正是停擺事故的成因"
    )


def test_try_claim_succeeds_only_when_expected_matches(store, ns):
    """✅ 庚-17（A-42）：原子先搶先贏——expected 與現值相符才更新並回 True；
    已被別的 worker 搶走（現值變了）回 False 且不覆寫。"""
    seed = datetime(2026, 7, 12, 3, 0, tzinfo=TPE)
    now = datetime(2026, 7, 13, 3, 0, tzinfo=TPE)
    store.set_last_run(f"{ns}job", seed)
    assert store.try_claim(f"{ns}job", expected=seed, now=now) is True
    got = store.get_last_run(f"{ns}job")
    assert got is not None and got.timestamp() == now.timestamp()
    # 第二個 worker 拿著過時的 expected 來搶 → 失敗、狀態不動。
    later = datetime(2026, 7, 14, 3, 0, tzinfo=TPE)
    assert store.try_claim(f"{ns}job", expected=seed, now=later) is False
    got2 = store.get_last_run(f"{ns}job")
    assert got2 is not None and got2.timestamp() == now.timestamp()
