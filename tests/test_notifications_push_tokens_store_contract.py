"""PushTokenStore 合約：Fake 與 Pg 兩個 adapter 對同一情境須給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`＋`KINSUN_TEST_DATABASE_URL`（連獨立測試庫）。
斷言以 `ns` 前綴 scope 到本測試自己的資料。push_token_id 與 updated_at 在 Fake
為合成值，除「排序」外不對其斷言。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.accounts.models import PrincipalType
from kinsun.notifications.push_tokens import FakePushTokenStore, PgPushTokenStore

TPE = timezone(timedelta(hours=8))
FIXED_CLOCK = datetime(2026, 7, 29, 9, 0, tzinfo=TPE)


@pytest.fixture(params=["fake", "pg"])
def store(request, ns):
    if request.param == "pg":
        ids = (f"{ns}pt{i}" for i in count(1))
        # 時鐘每次呼叫前進一秒：固定時鐘會讓同一測試內的多筆 updated_at 相等，
        # 「最近先」就變成資料庫回傳順序的賭博（Fake 用序號所以永遠是對的，
        # 只有 Pg 會偶爾紅）。這是測試的問題，不是 store 的。
        ticks = count(0)
        return PgPushTokenStore(
            request.getfixturevalue("pg_database"),
            clock=lambda: FIXED_CLOCK + timedelta(seconds=next(ticks)),
            new_id=lambda: next(ids),
        )
    return FakePushTokenStore()


def test_save_then_list(store, ns):
    store.save(f"{ns}tok1", PrincipalType.ELDER, f"{ns}e1", "android")

    rows = store.list_for_principal(PrincipalType.ELDER, f"{ns}e1")

    assert [r.token for r in rows] == [f"{ns}tok1"]
    assert rows[0].platform == "android"
    assert rows[0].principal_id == f"{ns}e1"


def test_one_principal_many_devices(store, ns):
    """長輩可能同時有手機與平板；兩台都要收得到提醒。"""
    store.save(f"{ns}tokA", PrincipalType.ELDER, f"{ns}e2", "android")
    store.save(f"{ns}tokB", PrincipalType.ELDER, f"{ns}e2", "ios")

    rows = store.list_for_principal(PrincipalType.ELDER, f"{ns}e2")

    assert {r.token for r in rows} == {f"{ns}tokA", f"{ns}tokB"}


def test_same_token_rebinds_to_new_principal(store, ns):
    """換人用同一台裝置：token 改綁，絕不可留兩列——否則提醒會送給前一位使用者。"""
    store.save(f"{ns}tokC", PrincipalType.ELDER, f"{ns}old", "android")
    store.save(f"{ns}tokC", PrincipalType.GUARDIAN, f"{ns}new", "android")

    assert store.list_for_principal(PrincipalType.ELDER, f"{ns}old") == []
    rows = store.list_for_principal(PrincipalType.GUARDIAN, f"{ns}new")
    assert [r.token for r in rows] == [f"{ns}tokC"]


def test_list_scoped_by_principal_type(store, ns):
    """同一個 id 字串在長輩與家屬各存一筆時不可互相污染。"""
    store.save(f"{ns}tokD", PrincipalType.ELDER, f"{ns}same", "android")
    store.save(f"{ns}tokE", PrincipalType.GUARDIAN, f"{ns}same", "android")

    assert [r.token for r in store.list_for_principal(PrincipalType.ELDER, f"{ns}same")] == [
        f"{ns}tokD"
    ]


def test_newest_first(store, ns):
    for i in range(3):
        store.save(f"{ns}tokF{i}", PrincipalType.ELDER, f"{ns}e3", "android")

    rows = store.list_for_principal(PrincipalType.ELDER, f"{ns}e3")

    assert [r.token for r in rows] == [f"{ns}tokF2", f"{ns}tokF1", f"{ns}tokF0"]


def test_remove(store, ns):
    store.save(f"{ns}tokG", PrincipalType.ELDER, f"{ns}e4", "android")

    store.remove(f"{ns}tokG")

    assert store.list_for_principal(PrincipalType.ELDER, f"{ns}e4") == []


def test_remove_unknown_token_is_noop(store, ns):
    """Expo 可能對已清掉的 token 再回一次 DeviceNotRegistered，重複刪不可炸。"""
    store.remove(f"{ns}never-existed")


def test_unknown_principal_returns_empty(store, ns):
    assert store.list_for_principal(PrincipalType.ELDER, f"{ns}nobody") == []
