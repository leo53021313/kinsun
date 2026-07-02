import os
import uuid
from datetime import datetime, timedelta, timezone
from itertools import count

import pytest

from kinsun.safety.tiers import RiskAssessment, RiskTier

TPE = timezone(timedelta(hours=8))


@pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")
def test_pg_risk_events_round_trip():
    from kinsun.db import Database, ensure_schema
    from kinsun.safety.events import PgRiskEventStore

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    line_user_id = f"it-{uuid.uuid4().hex}"
    ids = (f"re{i}" for i in count(1))
    times = iter([datetime(2026, 7, 10, 9, tzinfo=TPE), datetime(2026, 7, 10, 10, tzinfo=TPE)])
    store = PgRiskEventStore(
        Database.open(url), clock=lambda: next(times), new_id=lambda: next(ids)
    )
    store.record(line_user_id, RiskAssessment(RiskTier.L2, 0.9, "胸痛"))
    store.record(line_user_id, RiskAssessment(RiskTier.L3, 0.95, "昏倒"))
    events = store.list_for_line_user(line_user_id)
    assert [e.tier for e in events] == [RiskTier.L3, RiskTier.L2]
    assert events[0].reason == "昏倒"
