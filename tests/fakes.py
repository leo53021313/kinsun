"""單元測試用的記憶體替身（不碰任何 DB／網路）。"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime

from kinsun.llm import Message
from kinsun.medications.store import FakeMedicationStore as FakeMedicationStore
from kinsun.memory.shortterm import FakeMemoryStore as FakeMemoryStore
from kinsun.observability.models import (
    AsrCall,
    ElderActivity,
    FeedItem,
    HourlyCount,
    LlmCall,
    OverviewStats,
    Reply,
    StageStats,
    TimelineItem,
    Trace,
    TraceRiskEvent,
    TtsCall,
    WebhookEvent,
)
from kinsun.reports.reminders import ReminderLog
from kinsun.reports.summaries import ConversationSummary
from kinsun.safety.events import RiskEvent


class FakeLongTermStore:
    def __init__(self, search_result: str = "") -> None:
        self.added: list[tuple[str, list[Message], str]] = []
        self._search_result = search_result

    def add(
        self, line_user_id: str, messages: list[Message], *, provenance: str = "self_claimed"
    ) -> None:
        self.added.append((line_user_id, list(messages), provenance))

    def search(self, line_user_id: str, query: str, *, top_k: int = 5) -> str:
        return self._search_result


class FakeAccountStore:
    def __init__(self) -> None:
        self.elders = {}
        self.guardians = {}
        self.guardians_by_line = {}
        self.elder_guardians = {}
        self.consents = {}
        self.invites = {}

    @contextmanager
    def transaction(self):
        yield None

    def save_elder(self, elder, *, tx=None):
        self.elders[elder.elder_id] = elder

    def get_elder(self, elder_id):
        return self.elders.get(elder_id)

    def save_guardian(self, g, *, tx=None):
        self.guardians[g.guardian_id] = g
        self.guardians_by_line[g.line_user_id] = g

    def get_guardian_by_line(self, line_user_id):
        return self.guardians_by_line.get(line_user_id)

    def get_elder_by_line(self, line_user_id):
        for elder in self.elders.values():
            if elder.line_user_id == line_user_id:
                return elder
        return None

    def get_guardian(self, guardian_id):
        return self.guardians.get(guardian_id)

    def save_elder_guardian(self, eg, *, tx=None):
        self.elder_guardians[(eg.elder_id, eg.guardian_id)] = eg

    def get_elder_guardian(self, elder_id, guardian_id):
        return self.elder_guardians.get((elder_id, guardian_id))

    def list_elder_guardians(self, elder_id):
        rows = [v for (e, _), v in self.elder_guardians.items() if e == elder_id]
        return sorted(rows, key=lambda x: x.escalation_order)

    def elder_ids_of_guardian(self, guardian_id):
        return sorted(e for (e, g) in self.elder_guardians if g == guardian_id)

    def save_consent(self, c, *, tx=None):
        self.consents[c.elder_id] = c

    def get_consent(self, elder_id):
        return self.consents.get(elder_id)

    def save_invite(self, i, *, tx=None):
        self.invites[i.code] = i

    def get_invite(self, code):
        return self.invites.get(code)


class FakeBindingSessionStore:
    def __init__(self) -> None:
        self._sessions = {}

    def get(self, line_user_id):
        return self._sessions.get(line_user_id)

    def save(self, session):
        self._sessions[session.line_user_id] = session

    def delete(self, line_user_id):
        self._sessions.pop(line_user_id, None)


class FakeScheduleStateStore:
    def __init__(self) -> None:
        self._last: dict[str, datetime] = {}

    def get_last_run(self, job_name: str) -> datetime | None:
        return self._last.get(job_name)

    def set_last_run(self, job_name: str, when: datetime) -> None:
        self._last[job_name] = when


class FakeAppointmentStore:
    def __init__(self) -> None:
        self._appts = {}

    def save(self, appt):
        self._appts[appt.appointment_id] = appt

    def list_for_elder(self, elder_id):
        rows = [a for a in self._appts.values() if a.elder_id == elder_id]
        return sorted(rows, key=lambda a: a.date)

    def list_for_date(self, date):
        return [a for a in self._appts.values() if a.date == date]

    def remove(self, appointment_id):
        self._appts.pop(appointment_id, None)


class FakeRiskEventStore:
    def __init__(self) -> None:
        self.recorded: list[tuple] = []
        self.recorded_trace_ids: list[str | None] = []

    def record(self, line_user_id, assessment, *, trace_id=None):
        self.recorded.append((line_user_id, assessment))
        self.recorded_trace_ids.append(trace_id)

    def list_for_line_user(self, line_user_id):
        return [
            RiskEvent(str(i), s, a.tier, a.reason, float(i))
            for i, (s, a) in enumerate(self.recorded)
            if s == line_user_id
        ]


class FakeReminderLogStore:
    def __init__(self) -> None:
        self.recorded: list[tuple] = []

    def record(self, elder_id, kind, content):
        self.recorded.append((elder_id, kind, content))

    def list_for_elder(self, elder_id):
        return [
            ReminderLog(str(i), e, k, c, float(i))
            for i, (e, k, c) in enumerate(self.recorded)
            if e == elder_id
        ]


class FakeConversationSummaryStore:
    def __init__(self) -> None:
        self._rows: dict[tuple, str] = {}

    def save(self, line_user_id, date, content):
        self._rows[(line_user_id, date)] = content

    def list_for_line_user(self, line_user_id):
        items = sorted(
            ((d, c) for (s, d), c in self._rows.items() if s == line_user_id),
            key=lambda x: x[0],
            reverse=True,
        )
        return [ConversationSummary(line_user_id, d, c, 0.0) for d, c in items]


class FakeTraceStore:
    """TraceStore 測試替身：記錄存於公開 list；now 屬性控制 created_at。

    seed_* 方法模擬既有表（turns／reminder_logs／risk_events／elders）資料，
    供查詢面（feed／timeline／overview）測試播種。
    """

    def __init__(self) -> None:
        self.now = 0.0
        self._seq = 0
        self.webhook_events: list[WebhookEvent] = []
        self.asr_calls: list[AsrCall] = []
        self.llm_calls: list[LlmCall] = []
        self.tts_calls: list[TtsCall] = []
        self.replies: list[Reply] = []
        # (line_user_id, role, content, created_at)
        self.turns: list[tuple[str, str, str, float]] = []
        # (elder_id, kind, content, created_at)
        self.reminders: list[tuple[str, str, str, float]] = []
        # (line_user_id, tier, reason, created_at, trace_id)
        self.risks: list[tuple[str, int, str, float, str | None]] = []
        # (elder_id, name, line_user_id)
        self.elders: list[tuple[str, str, str]] = []

    def _next_id(self) -> str:
        self._seq += 1
        return f"obs{self._seq}"

    # --- 播種（模擬既有表） ---

    def seed_turn(self, line_user_id: str, role: str, content: str, created_at: float) -> None:
        self.turns.append((line_user_id, role, content, created_at))

    def seed_reminder(self, elder_id: str, kind: str, content: str, created_at: float) -> None:
        self.reminders.append((elder_id, kind, content, created_at))

    def seed_risk(
        self,
        line_user_id: str,
        tier: int,
        reason: str,
        created_at: float,
        trace_id: str | None = None,
    ) -> None:
        self.risks.append((line_user_id, tier, reason, created_at, trace_id))

    def seed_elder(self, elder_id: str, name: str, line_user_id: str) -> None:
        self.elders.append((elder_id, name, line_user_id))

    def _elder_name_by_line(self, line_user_id: str) -> str:
        return next((n for _, n, lu in self.elders if lu == line_user_id), "")

    # --- record 面 ---

    def record_webhook_event(
        self, *, trace_id, line_user_id, event_type, message_type, payload
    ) -> None:
        self.webhook_events.append(
            WebhookEvent(
                self._next_id(), trace_id, line_user_id, event_type, message_type, payload, self.now
            )
        )

    def record_asr_call(
        self,
        *,
        trace_id,
        line_user_id,
        status,
        latency_ms,
        transcript,
        source_audio_url,
        error_message,
    ) -> None:
        self.asr_calls.append(
            AsrCall(
                self._next_id(),
                trace_id,
                line_user_id,
                status,
                latency_ms,
                transcript,
                source_audio_url,
                error_message,
                self.now,
            )
        )

    def record_llm_call(
        self,
        *,
        trace_id,
        line_user_id,
        status,
        latency_ms,
        model_name,
        input_tokens,
        output_tokens,
        content,
        error_message,
    ) -> None:
        self.llm_calls.append(
            LlmCall(
                self._next_id(),
                trace_id,
                line_user_id,
                status,
                latency_ms,
                model_name,
                input_tokens,
                output_tokens,
                content,
                error_message,
                self.now,
            )
        )

    def record_tts_call(
        self, *, trace_id, line_user_id, status, latency_ms, content, error_message
    ) -> None:
        self.tts_calls.append(
            TtsCall(
                self._next_id(),
                trace_id,
                line_user_id,
                status,
                latency_ms,
                content,
                error_message,
                self.now,
            )
        )

    def record_reply(self, *, trace_id, line_user_id, kind, status, latency_ms, audio_url) -> None:
        self.replies.append(
            Reply(
                self._next_id(),
                trace_id,
                line_user_id,
                kind,
                status,
                latency_ms,
                audio_url,
                self.now,
            )
        )

    # --- 查詢面 ---

    def get_trace(self, trace_id: str) -> Trace | None:
        webhook_event = next((e for e in self.webhook_events if e.trace_id == trace_id), None)
        asr_call = next((c for c in self.asr_calls if c.trace_id == trace_id), None)
        llm_calls = [c for c in self.llm_calls if c.trace_id == trace_id]
        tts_call = next((c for c in self.tts_calls if c.trace_id == trace_id), None)
        reply = next((r for r in self.replies if r.trace_id == trace_id), None)
        risk_events = [
            TraceRiskEvent(t, reason, ts) for _, t, reason, ts, tid in self.risks if tid == trace_id
        ]
        if not any([webhook_event, asr_call, llm_calls, tts_call, reply, risk_events]):
            return None
        line_user_id = next(
            (x.line_user_id for x in [webhook_event, asr_call, tts_call, reply] if x),
            llm_calls[0].line_user_id if llm_calls else "",
        )
        return Trace(
            trace_id, line_user_id, webhook_event, asr_call, llm_calls, tts_call, reply, risk_events
        )

    def list_feed(self, *, after: float, limit: int) -> list[FeedItem]:
        items: list[FeedItem] = []
        for line_user_id, role, content, ts in self.turns:
            if ts > after:
                items.append(
                    FeedItem(
                        "turn",
                        line_user_id,
                        self._elder_name_by_line(line_user_id),
                        role,
                        content,
                        None,
                        None,
                        ts,
                    )
                )
        for elder_id, _kind, content, ts in self.reminders:
            if ts > after:
                row = next((e for e in self.elders if e[0] == elder_id), None)
                items.append(
                    FeedItem(
                        "reminder",
                        row[2] if row else "",
                        row[1] if row else "",
                        "",
                        content,
                        None,
                        None,
                        ts,
                    )
                )
        for line_user_id, tier, reason, ts, tid in self.risks:
            if ts > after:
                items.append(
                    FeedItem(
                        "risk",
                        line_user_id,
                        self._elder_name_by_line(line_user_id),
                        "",
                        reason,
                        tier,
                        tid,
                        ts,
                    )
                )
        items.sort(key=lambda i: i.created_at, reverse=True)
        return items[:limit]

    def list_timeline_for_elder(
        self, *, elder_id: str, line_user_id: str, start: float, end: float
    ) -> list[TimelineItem]:
        items: list[TimelineItem] = []
        for lu, role, content, ts in self.turns:
            if lu == line_user_id and start <= ts < end:
                items.append(TimelineItem("turn", role, content, None, None, "", ts))
        for eid, _kind, content, ts in self.reminders:
            if eid == elder_id and start <= ts < end:
                items.append(TimelineItem("reminder", "", content, None, None, "", ts))
        for lu, tier, reason, ts, tid in self.risks:
            if lu == line_user_id and start <= ts < end:
                items.append(TimelineItem("risk", "", reason, tier, tid, "", ts))
        for c in self.asr_calls:
            if c.line_user_id == line_user_id and start <= c.created_at < end:
                items.append(
                    TimelineItem(
                        "voice",
                        "user",
                        c.transcript,
                        None,
                        c.trace_id,
                        c.source_audio_url,
                        c.created_at,
                    )
                )
        for r in self.replies:
            if r.line_user_id == line_user_id and r.audio_url and start <= r.created_at < end:
                items.append(
                    TimelineItem(
                        "voice", "assistant", "", None, r.trace_id, r.audio_url, r.created_at
                    )
                )
        items.sort(key=lambda i: i.created_at)
        return items

    def list_elders_with_last_active(self) -> list[ElderActivity]:
        result = []
        for elder_id, name, line_user_id in sorted(self.elders, key=lambda e: e[1]):
            actives = [ts for lu, _, _, ts in self.turns if lu == line_user_id]
            result.append(
                ElderActivity(elder_id, name, line_user_id, max(actives) if actives else None)
            )
        return result

    def get_overview_stats(self, *, today_start: float, hourly_start: float) -> OverviewStats:
        today_turns = [t for t in self.turns if t[3] >= today_start]
        stages = []
        for stage, calls in (
            ("asr", self.asr_calls),
            ("llm", self.llm_calls),
            ("tts", self.tts_calls),
        ):
            recent = [c for c in calls if c.created_at >= today_start]
            lats = sorted(c.latency_ms for c in recent)
            p95 = lats[max(0, -(-95 * len(lats) // 100) - 1)] if lats else 0.0
            stages.append(
                StageStats(
                    stage,
                    len(recent),
                    sum(1 for c in recent if c.status != "ok"),
                    sum(lats) / len(lats) if lats else 0.0,
                    float(p95),
                )
            )
        llm_recent = [c for c in self.llm_calls if c.created_at >= today_start]
        buckets: dict[float, int] = {}
        for t in self.turns:
            if t[3] >= hourly_start:
                bucket = (t[3] // 3600) * 3600
                buckets[bucket] = buckets.get(bucket, 0) + 1
        return OverviewStats(
            turn_count=len(today_turns),
            risk_event_count=sum(1 for r in self.risks if r[3] >= today_start),
            active_elder_count=len({t[0] for t in today_turns}),
            llm_input_tokens=sum(c.input_tokens or 0 for c in llm_recent),
            llm_output_tokens=sum(c.output_tokens or 0 for c in llm_recent),
            stages=stages,
            hourly_turns=[HourlyCount(h, n) for h, n in sorted(buckets.items())],
        )

    def purge_older_than(self, cutoff: float) -> None:
        self.webhook_events = [e for e in self.webhook_events if e.created_at >= cutoff]
        self.asr_calls = [c for c in self.asr_calls if c.created_at >= cutoff]
        self.llm_calls = [c for c in self.llm_calls if c.created_at >= cutoff]
        self.tts_calls = [c for c in self.tts_calls if c.created_at >= cutoff]
        self.replies = [r for r in self.replies if r.created_at >= cutoff]
