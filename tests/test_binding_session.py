import os

import pytest

from kinsun.binding.session import BindingSession, BindingState


def test_binding_state_values():
    assert BindingState.MENU.value == "menu"
    assert BindingState.AWAIT_CONFIRM.value == "confirm"


def test_fake_session_round_trip():
    from tests.fakes import FakeBindingSessionStore

    store = FakeBindingSessionStore()
    assert store.get("U-1") is None
    store.save(BindingSession("U-1", BindingState.MENU, {"x": 1}, 100.0))
    got = store.get("U-1")
    assert got.state == BindingState.MENU
    assert got.data == {"x": 1}
    store.delete("U-1")
    assert store.get("U-1") is None


@pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")
def test_pg_session_round_trip():
    from kinsun.binding.session import PgBindingSessionStore
    from kinsun.db import ensure_schema

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    store = PgBindingSessionStore(url)
    store.save(BindingSession("U-pg", BindingState.AWAIT_CODE, {"k": "v"}, 123.0))
    got = store.get("U-pg")
    assert got.state == BindingState.AWAIT_CODE
    assert got.data == {"k": "v"}
    store.delete("U-pg")
    assert store.get("U-pg") is None
