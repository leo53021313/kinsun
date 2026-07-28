from contextlib import contextmanager

import pytest

from kinsun.db import CLI_POOL_MAX_SIZE, Database, StoreError, _Errors


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeConn:
    def __init__(self, rows=None, boom=False):
        self.rows = rows or []
        self.boom = boom
        self.calls = []
        self.committed = False
        self.tx_entered = False

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        if self.boom:
            raise RuntimeError("db down")
        return _FakeCursor(self.rows)

    def commit(self):
        self.committed = True

    @contextmanager
    def transaction(self):
        self.tx_entered = True
        yield


class _FakePool:
    def __init__(self, conn):
        self._conn = conn
        self.closed = False

    @contextmanager
    def connection(self):
        yield self._conn

    def close(self):
        self.closed = True


def test_execute_commits():
    conn = _FakeConn()
    db = Database(_FakePool(conn))
    db.execute("INSERT INTO t VALUES (%s)", ("a",))
    assert conn.calls == [("INSERT INTO t VALUES (%s)", ("a",))]
    assert conn.committed is True


def test_query_returns_rows():
    conn = _FakeConn(rows=[("x",), ("y",)])
    db = Database(_FakePool(conn))
    assert db.query("SELECT c FROM t") == [("x",), ("y",)]
    assert db.query_one("SELECT c FROM t") == ("x",)


def test_failure_raises_store_error():
    db = Database(_FakePool(_FakeConn(boom=True)))
    with pytest.raises(StoreError):
        db.execute("INSERT INTO t VALUES (%s)", ("a",))


def test_query_failure_raises_store_error():
    db = Database(_FakePool(_FakeConn(boom=True)))
    with pytest.raises(StoreError):
        db.query("SELECT 1")


def test_query_one_failure_raises_store_error():
    db = Database(_FakePool(_FakeConn(boom=True)))
    with pytest.raises(StoreError):
        db.query_one("SELECT 1")


def test_transaction_yields_executor():
    conn = _FakeConn(rows=[("ok",)])
    db = Database(_FakePool(conn))
    with db.transaction() as tx:
        tx.execute("INSERT INTO t VALUES (%s)", ("a",))
        assert tx.query_one("SELECT c FROM t") == ("ok",)
    assert conn.tx_entered is True


def test_close_closes_pool():
    pool = _FakePool(_FakeConn())
    Database(pool).close()
    assert pool.closed is True


def test_errors_translates_store_error():
    class _Boom:
        def execute(self, sql, params=()):
            raise StoreError("boom")

        def query(self, sql, params=()):
            raise StoreError("boom")

        def query_one(self, sql, params=()):
            raise StoreError("boom")

        @contextmanager
        def transaction(self):
            raise StoreError("boom")
            yield

    wrapped = _Errors(_Boom(), lambda m: ValueError(f"translated:{m}"))
    with pytest.raises(ValueError, match="translated:boom"):
        wrapped.execute("X")
    with pytest.raises(ValueError, match="translated:boom"):
        wrapped.query("X")
    with pytest.raises(ValueError, match="translated:boom"):
        wrapped.query_one("X")
    with pytest.raises(ValueError, match="translated:boom"):
        with wrapped.transaction():
            pass


def test_open_for_cli_uses_a_small_pool(monkeypatch):
    """CLI（ingest／migrate／consolidation…）只借最小額度，不與線上服務搶連線。

    2026-07-28 實證：Supabase pooler session mode 上限 15，常駐服務齊跑時
    CLI 用預設 5 條會借不到連線（EMAXCONNSESSION），整個 ingest 起不來。
    """
    captured: dict[str, int] = {}

    class _FakePool:
        def __init__(self, url, *, min_size, max_size, open, kwargs):
            captured["min_size"] = min_size
            captured["max_size"] = max_size

    monkeypatch.setattr("kinsun.db.ConnectionPool", _FakePool)

    Database.open_for_cli("postgresql://x/y")

    assert captured["max_size"] == CLI_POOL_MAX_SIZE
    # 上限 15、常駐服務 4 進程各 DATABASE_POOL_MAX_SIZE(3)＝12，CLI 只剩 3 條可用。
    assert captured["max_size"] <= 3
