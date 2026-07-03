import os
from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")

TPE = timezone(timedelta(hours=8))


def test_pg_round_trip():
    from kinsun.db import Database, ensure_schema
    from kinsun.scheduler.state import PgScheduleStateStore

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    store = PgScheduleStateStore(Database.open(url), TPE)
    job = f"it-job-{os.getpid()}"
    assert store.get_last_run(f"{job}-未設") is None
    when = datetime(2026, 6, 29, 3, 0, tzinfo=TPE)
    store.set_last_run(job, when)
    assert store.get_last_run(job) == when
