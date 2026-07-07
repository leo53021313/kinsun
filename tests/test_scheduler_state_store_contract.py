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
