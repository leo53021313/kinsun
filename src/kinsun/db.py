"""共用 Postgres 連線與建表 DDL（Supabase）。"""

from __future__ import annotations

import psycopg

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


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url)


def ensure_schema(database_url: str) -> None:
    with connect(database_url) as conn:
        conn.execute(MEMORY_DDL)
        conn.execute(ACCOUNTS_DDL)
        conn.execute(BINDING_DDL)
        conn.commit()
