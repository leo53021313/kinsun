import os
import uuid
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

TPE = timezone(timedelta(hours=8))


@pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")
def test_pg_reminder_logs_round_trip():
    from kinsun.db import Database, ensure_schema
    from kinsun.reports.reminders import PgReminderLogStore

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    elder_id = f"it-{uuid.uuid4().hex}"
    ids = (f"rl{i}" for i in count(1))
    times = iter([datetime(2026, 7, 10, 9, tzinfo=TPE), datetime(2026, 7, 10, 10, tzinfo=TPE)])
    store = PgReminderLogStore(Database.open(url), clock=lambda: next(times), new_id=lambda: next(ids))
    store.record(elder_id, "medication", "早上用藥：A")
    store.record(elder_id, "appointment", "明天回診：B")
    rows = store.list_for_elder(elder_id)
    assert [r.kind for r in rows] == ["appointment", "medication"]
    assert rows[0].content == "明天回診：B"
