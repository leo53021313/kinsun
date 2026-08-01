"""AppNotificationStore 合約：Fake 與 Pg 兩個 adapter 對同一情境須給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`＋`KINSUN_TEST_DATABASE_URL`（連獨立測試庫）。
斷言以 `ns` 前綴 scope 到本測試自己的資料。app_notification_id 與 created_at
在 Fake 為合成值，除「排序」外不對其斷言。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.notifications.models import NotificationSeverity
from kinsun.notifications.store import FakeAppNotificationStore, PgAppNotificationStore

TPE = timezone(timedelta(hours=8))
FIXED_CLOCK = datetime(2026, 7, 9, 9, 0, tzinfo=TPE)


@pytest.fixture(params=["fake", "pg"])
def store(request, ns):
    if request.param == "pg":
        ids = (f"{ns}an{i}" for i in count(1))
        return PgAppNotificationStore(
            request.getfixturevalue("pg_database"),
            clock=lambda: FIXED_CLOCK,
            new_id=lambda: next(ids),
        )
    return FakeAppNotificationStore()


def test_record_then_list_returns_content(store, ns):
    ext = f"{ns}ext1"
    store.record(ext, "阿蘭提到跌倒，請留意")
    got = store.list_for_external_ids([ext])
    assert [n.content for n in got] == ["阿蘭提到跌倒，請留意"]
    assert got[0].external_id == ext


def test_list_aggregates_multiple_external_ids_and_excludes_others(store, ns):
    a, b, other = f"{ns}extA", f"{ns}extB", f"{ns}extC"
    store.record(a, "通知A")
    store.record(b, "通知B")
    store.record(other, "別人的")
    contents = {n.content for n in store.list_for_external_ids([a, b])}
    assert contents == {"通知A", "通知B"}


def test_list_recent_first_with_limit(store, ns):
    ext = f"{ns}ext1"
    for i in range(3):
        store.record(ext, f"第{i}則")
    got = store.list_for_external_ids([ext], limit=2)
    assert len(got) == 2
    # 最近先：created_at 遞減（同刻時不強制序，僅驗排序鍵單調不升）。
    assert got[0].created_at >= got[1].created_at


def test_list_empty_ids_returns_empty(store, ns):
    assert store.list_for_external_ids([]) == []


# ── 呈現分級（2026-08-01 Leo 裁決）──────────────────────────────


def test_severity_defaults_to_notice(store, ns):
    """不指定＝一般通知。用藥提醒、主動關懷全部走這條，不可預設成 alert。"""
    ext = f"{ns}extSevDefault"
    store.record(ext, "阿嬤，早上該吃藥囉")
    assert store.list_for_external_ids([ext])[0].severity == NotificationSeverity.NOTICE


def test_severity_alert_round_trips(store, ns):
    """危急警報存進去、讀出來仍是 alert——這是整條線的存在理由。"""
    ext = f"{ns}extSevAlert"
    store.record(ext, "王阿嬤剛剛說：「我跌倒了」", severity=NotificationSeverity.ALERT)
    assert store.list_for_external_ids([ext])[0].severity == NotificationSeverity.ALERT


def test_severity_is_per_row_not_per_external_id(store, ns):
    """同一個人的兩則通知各有各的分級——不可被最後一則覆寫或整批同化。

    ⚠️ 這正是展示現場的形狀：家屬同一支手機上，早上的用藥提醒與剛剛的危急警報
    並排躺著，一則白、一則紅。
    """
    ext = f"{ns}extSevMixed"
    store.record(ext, "早上該吃藥囉")
    store.record(ext, "王阿嬤剛剛說：「我跌倒了」", severity=NotificationSeverity.ALERT)
    by_content = {n.content: n.severity for n in store.list_for_external_ids([ext])}
    assert by_content == {
        "早上該吃藥囉": NotificationSeverity.NOTICE,
        "王阿嬤剛剛說：「我跌倒了」": NotificationSeverity.ALERT,
    }
