import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")


def _store():
    from kinsun.db import ensure_schema
    from kinsun.memory.store import PgMemoryStore

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    tz = ZoneInfo("Asia/Taipei")
    return PgMemoryStore(url, clock=lambda: datetime.now(tz), max_turns=20)


def test_append_and_recent_roundtrip():
    from kinsun.llm import Message

    store = _store()
    sid = f"it-{os.getpid()}"
    store.append(sid, Message("user", "你好"))
    store.append(sid, Message("assistant", "您好"))
    msgs = store.recent(sid)
    assert [m.text for m in msgs][-2:] == ["你好", "您好"]
    assert store.last_active(sid) is not None
    assert sid in store.sessions()


def test_previous_day_excludes_today():
    from kinsun.llm import Message

    store = _store()
    sid = f"it-prevday-{os.getpid()}"
    # 今天剛寫入的對話不應落在「前一天」整理區間內。
    store.append(sid, Message("user", "今天說的"))
    assert store.previous_day(sid) == []
