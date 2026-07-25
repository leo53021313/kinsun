"""schedules 表的 schema 合約（連真庫；KINSUN_IT=1 才跑）。

既有庫升級路徑必測：空的測試庫測不到舊表升級，故斷言以「欄位齊備＋索引存在」
表述，且重跑 ensure_schema 必須冪等。
"""

from __future__ import annotations

from kinsun.db import ensure_schema

_EXPECTED_COLUMNS = {
    "schedule_id",
    "group_id",
    "elder_id",
    "kind",
    "title",
    "repeat_kind",
    "scheduled_at",
    "repeat_time",
    "repeat_weekday",
    "event_at",
    "audience",
    "created_by",
    "created_at",
    "cancelled_at",
    "settled_at",
    "fired_at",
}


def test_schedules_table_has_all_columns(pg_database):
    rows = pg_database.query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'schedules'"
    )
    assert _EXPECTED_COLUMNS <= {row[0] for row in rows}


def test_schedules_indexes_exist(pg_database):
    rows = pg_database.query(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'schedules'"
    )
    names = {row[0] for row in rows}
    assert "idx_schedules_elder_active" in names
    assert "idx_schedules_group" in names
    assert "idx_schedules_repeat" in names
    assert "idx_schedules_due_once" in names


def test_ensure_schema_is_idempotent(pg_database, pg_url):
    # pg_database fixture 已跑過一次 ensure_schema；這裡再跑兩次，任一次拋例外即失敗。
    ensure_schema(pg_url)
    ensure_schema(pg_url)
    assert pg_database.query("SELECT count(*) FROM schedules")[0][0] >= 0
