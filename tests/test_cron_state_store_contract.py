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

from kinsun.cron.state import FakeScheduleStateStore, PgScheduleStateStore

TPE = timezone(timedelta(hours=8))
FIXED = datetime(2026, 7, 27, 3, 0, tzinfo=TPE)


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


# ── 成功訊號（2026-07-27）──
#
# `try_claim` 寫的是「認領」不是「成功」（見 PgScheduleStateStore.try_claim 的 docstring
# 與 Scheduler._claim_if_due：搶占＝寫入 last_run，故 job 失敗也算已跑）。於是「每輪都
# 認領成功、每輪都拋例外」的 job，`/admin/jobs` 的逾期判斷一律顯示健康。
# 加一個獨立的成功訊號，兩件事才分得開。⚠️ 不可改 last_run_at 的語意——
# at-most-once 的原子搶占（庚-17／A-42）靠它，test_cron_scheduler 明文守住「失敗仍標記」。


def test_success_is_recorded_independently_of_last_run(store, ns):
    job = f"{ns}job"
    store.set_last_run(job, FIXED)
    assert store.get_last_success(job) is None  # 只認領過、還沒成功過
    store.record_success(job, FIXED)
    assert store.get_last_success(job).timestamp() == FIXED.timestamp()
    assert store.get_last_run(job).timestamp() == FIXED.timestamp()


def test_last_success_is_none_for_a_job_that_never_ran(store, ns):
    assert store.get_last_success(f"{ns}never") is None


def test_recording_success_does_not_move_last_run(store, ns):
    """兩個欄位必須各自獨立：成功訊號不得干擾認領語意。"""
    job = f"{ns}job2"
    store.set_last_run(job, FIXED)
    later = FIXED + timedelta(hours=1)
    store.record_success(job, later)
    assert store.get_last_run(job).timestamp() == FIXED.timestamp()
    assert store.get_last_success(job).timestamp() == later.timestamp()
