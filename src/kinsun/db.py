"""共用 Postgres 連線、連線池與建表 DDL（Supabase）。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Protocol

import psycopg
from psycopg_pool import ConnectionPool

MEMORY_DDL = (
    "CREATE TABLE IF NOT EXISTS turns ("
    "id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL, role TEXT NOT NULL, "
    "text TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_turns_session_created ON turns (session_id, created_at);"
)

ACCOUNTS_DDL = (
    "CREATE TABLE IF NOT EXISTS elders ("
    "elder_id TEXT PRIMARY KEY, name TEXT NOT NULL, line_user_id TEXT);"
    "CREATE TABLE IF NOT EXISTS guardians ("
    "guardian_id TEXT PRIMARY KEY, line_user_id TEXT NOT NULL UNIQUE, name TEXT NOT NULL);"
    "CREATE TABLE IF NOT EXISTS elder_guardians ("
    "elder_id TEXT NOT NULL, guardian_id TEXT NOT NULL, role TEXT NOT NULL, "
    "escalation_order INTEGER NOT NULL, can_view_transcript BOOLEAN NOT NULL, "
    "PRIMARY KEY (elder_id, guardian_id));"
    "CREATE TABLE IF NOT EXISTS consents ("
    "elder_id TEXT PRIMARY KEY, consent_by TEXT NOT NULL, version TEXT NOT NULL, "
    "granted_at DOUBLE PRECISION NOT NULL, revoked_at DOUBLE PRECISION);"
    "CREATE TABLE IF NOT EXISTS invites ("
    "code TEXT PRIMARY KEY, elder_id TEXT NOT NULL, role TEXT NOT NULL, "
    "expires_at DOUBLE PRECISION NOT NULL, max_attempts INTEGER NOT NULL, "
    "attempts INTEGER NOT NULL, used_at DOUBLE PRECISION);"
)

BINDING_DDL = (
    "CREATE TABLE IF NOT EXISTS binding_sessions ("
    "line_user_id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL, "
    "updated_at DOUBLE PRECISION NOT NULL);"
)

SCHEDULER_DDL = (
    "CREATE TABLE IF NOT EXISTS scheduler_state ("
    "job_name TEXT PRIMARY KEY, last_run_at DOUBLE PRECISION NOT NULL);"
)

MEDICATIONS_DDL = (
    "CREATE TABLE IF NOT EXISTS medications ("
    "med_id TEXT PRIMARY KEY, elder_id TEXT NOT NULL, name TEXT NOT NULL, slots TEXT NOT NULL);"
)

APPOINTMENTS_DDL = (
    "CREATE TABLE IF NOT EXISTS appointments ("
    "appt_id TEXT PRIMARY KEY, elder_id TEXT NOT NULL, "
    "appt_date TEXT NOT NULL, label TEXT NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_appt_date ON appointments (appt_date);"
)

RISK_EVENTS_DDL = (
    "CREATE TABLE IF NOT EXISTS risk_events ("
    "event_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, "
    "tier INTEGER NOT NULL, reason TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL);"
    "CREATE INDEX IF NOT EXISTS idx_risk_events_session_created "
    "ON risk_events (session_id, created_at);"
)


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def ensure_schema(database_url: str) -> None:
    with connect(database_url) as conn:
        conn.execute(MEMORY_DDL)
        conn.execute(ACCOUNTS_DDL)
        conn.execute(BINDING_DDL)
        conn.execute(SCHEDULER_DDL)
        conn.execute(MEDICATIONS_DDL)
        conn.execute(APPOINTMENTS_DDL)
        conn.execute(RISK_EVENTS_DDL)
        conn.commit()


class StoreError(Exception):
    """資料庫存取失敗（連線／執行／交易）；各 store 會翻成自己的領域錯誤。"""


class Executor(Protocol):
    """可執行 SQL 的對象：Database 本身或交易內的單一連線。"""

    def execute(self, sql: str, params: tuple = ()) -> None: ...
    def query(self, sql: str, params: tuple = ()) -> list[tuple]: ...
    def query_one(self, sql: str, params: tuple = ()) -> tuple | None: ...


class _ConnExecutor:
    """包一條交易連線並提供 Executor 介面（不自行 commit；交易結束統一提交）。"""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple = ()) -> None:
        self._conn.execute(sql, params)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> tuple | None:
        return self._conn.execute(sql, params).fetchone()


class Database:
    """連線池 ＋ 交易 ＋ 錯誤翻譯。所有方法失敗丟 StoreError。"""

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    @classmethod
    def open(cls, url: str, *, min_size: int = 1, max_size: int = 5) -> Database:
        return cls(ConnectionPool(url, min_size=min_size, max_size=max_size, open=True))

    def close(self) -> None:
        self._pool.close()

    def execute(self, sql: str, params: tuple = ()) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(sql, params)
                conn.commit()
        except StoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - 一律翻成 StoreError
            raise StoreError(str(exc)) from exc

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        try:
            with self._pool.connection() as conn:
                return conn.execute(sql, params).fetchall()
        except StoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StoreError(str(exc)) from exc

    def query_one(self, sql: str, params: tuple = ()) -> tuple | None:
        try:
            with self._pool.connection() as conn:
                return conn.execute(sql, params).fetchone()
        except StoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StoreError(str(exc)) from exc

    @contextmanager
    def transaction(self) -> Iterator[Executor]:
        try:
            with self._pool.connection() as conn, conn.transaction():
                yield _ConnExecutor(conn)
        except StoreError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StoreError(str(exc)) from exc


class _Errors:
    """把內層 Executor 丟的 StoreError 翻成某 store 的領域錯誤；本身也是 Executor。"""

    def __init__(self, inner: Executor, wrap: Callable[[str], Exception]) -> None:
        self._inner = inner
        self._wrap = wrap

    def execute(self, sql: str, params: tuple = ()) -> None:
        try:
            self._inner.execute(sql, params)
        except StoreError as exc:
            raise self._wrap(str(exc)) from exc

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        try:
            return self._inner.query(sql, params)
        except StoreError as exc:
            raise self._wrap(str(exc)) from exc

    def query_one(self, sql: str, params: tuple = ()) -> tuple | None:
        try:
            return self._inner.query_one(sql, params)
        except StoreError as exc:
            raise self._wrap(str(exc)) from exc

    @contextmanager
    def transaction(self) -> Iterator[Executor]:
        try:
            # _Errors 只用來包 Database（有 transaction()）；Executor Protocol 僅涵蓋三個基本操作
            with self._inner.transaction() as tx:  # type: ignore[attr-defined]
                yield _Errors(tx, self._wrap)
        except StoreError as exc:
            raise self._wrap(str(exc)) from exc
