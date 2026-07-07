"""BindingSessionStore 合約：Fake 與 Pg 兩個 adapter 必須對同一情境給出相同結果。

Fake 每次都跑；Pg 需 `KINSUN_IT=1`（連真庫）。斷言一律以 `ns` 前綴 scope 到
本測試自己的 line_user_id，才能在共用真庫上互不干擾。
"""

from __future__ import annotations

import pytest

from kinsun.binding.session import (
    BindingSession,
    BindingState,
    FakeBindingSessionStore,
    PgBindingSessionStore,
)


@pytest.fixture(params=["fake", "pg"])
def store(request):
    if request.param == "pg":
        return PgBindingSessionStore(request.getfixturevalue("pg_database"))
    return FakeBindingSessionStore()


def test_get_returns_none_before_save(store, ns):
    assert store.get(f"{ns}U1") is None


def test_save_then_get_round_trips(store, ns):
    line_user_id = f"{ns}U1"
    store.save(BindingSession(line_user_id, BindingState.AWAIT_CODE, {"k": "v"}, 123.0))
    got = store.get(line_user_id)
    assert got is not None
    assert got.line_user_id == line_user_id
    assert got.state == BindingState.AWAIT_CODE
    assert got.data == {"k": "v"}
    assert got.updated_at == 123.0


def test_save_upserts_on_conflict(store, ns):
    line_user_id = f"{ns}U1"
    store.save(BindingSession(line_user_id, BindingState.MENU, {"x": 1}, 100.0))
    store.save(BindingSession(line_user_id, BindingState.AWAIT_CONFIRM, {"x": 2}, 200.0))
    got = store.get(line_user_id)
    assert got is not None
    assert got.state == BindingState.AWAIT_CONFIRM
    assert got.data == {"x": 2}
    assert got.updated_at == 200.0


def test_delete_then_get_returns_none(store, ns):
    line_user_id = f"{ns}U1"
    store.save(BindingSession(line_user_id, BindingState.MENU, {}, 1.0))
    store.delete(line_user_id)
    assert store.get(line_user_id) is None
