from contextlib import contextmanager

import pytest

from kinsun.db import Database, StoreError, _Errors


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
