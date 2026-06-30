import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from kinsun.llm import Message
from kinsun.reports.summaries import summarize_day
from tests.fakes import FakeConversationSummaryStore

TPE = timezone(timedelta(hours=8))
NOW = datetime(2026, 7, 11, 3, 0, tzinfo=TPE)  # 凌晨 3 點，摘要前一天 7/10


class _ShortTerm:
    def __init__(self, turns):
        self._turns = turns

    def previous_day(self, session_id):
        return self._turns


class _StubSummarizer:
    def __init__(self, text="阿公今天聊天氣，心情不錯"):
        self.text = text
        self.calls = []

    def generate(self, *, system_prompt, messages):
        self.calls.append((system_prompt, messages))
        return self.text


def test_summarize_day_writes_summary():
    summaries = FakeConversationSummaryStore()
    turns = [Message("user", "今天天氣真好"), Message("assistant", "是啊")]
    summarize_day(
        "u1",
        short_term=_ShortTerm(turns),
        summarizer=_StubSummarizer(),
        summaries=summaries,
        clock=lambda: NOW,
    )
    rows = summaries.list_for_session("u1")
    assert len(rows) == 1
    assert rows[0].date == "2026-07-10"
    assert rows[0].content == "阿公今天聊天氣，心情不錯"


def test_summarize_day_skips_when_no_turns():
    summaries = FakeConversationSummaryStore()
    summarize_day(
        "u1",
        short_term=_ShortTerm([]),
        summarizer=_StubSummarizer(),
        summaries=summaries,
        clock=lambda: NOW,
    )
    assert summaries.list_for_session("u1") == []


@pytest.mark.skipif(os.environ.get("KINSUN_IT") != "1", reason="需雲端 key")
def test_pg_summary_upsert_and_list():
    from kinsun.db import Database, ensure_schema
    from kinsun.reports.summaries import PgConversationSummaryStore

    url = os.environ["DATABASE_URL"]
    ensure_schema(url)
    sid = f"it-{uuid.uuid4().hex}"
    store = PgConversationSummaryStore(Database.open(url), clock=lambda: NOW)
    store.upsert(sid, "2026-07-10", "v1")
    store.upsert(sid, "2026-07-10", "v2")  # 同日覆蓋
    store.upsert(sid, "2026-07-11", "今天")
    rows = store.list_for_session(sid)
    assert [r.date for r in rows] == ["2026-07-11", "2026-07-10"]
    assert rows[1].content == "v2"
