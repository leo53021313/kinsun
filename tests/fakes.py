"""單元測試用的記憶體替身（不碰任何 DB／網路）。

各 store 的 Fake 依三件套與其 Protocol＋Pg 同住原始碼（見各 store 檔），本檔僅保留
匯入轉出以相容既有 import。FakeLongTermStore 因長期記憶為 Mem0 語意檢索、非決定性，
不適用「兩 adapter 等價」合約，故仍定義於此、未納入合約掃描。
"""

from __future__ import annotations

from kinsun.accounts.store import FakeAccountStore as FakeAccountStore
from kinsun.appointments.store import FakeAppointmentStore as FakeAppointmentStore
from kinsun.binding.session import FakeBindingSessionStore as FakeBindingSessionStore
from kinsun.llm import Message
from kinsun.medications.store import FakeMedicationStore as FakeMedicationStore
from kinsun.memory.models import MemoryItem
from kinsun.memory.shortterm import FakeMemoryStore as FakeMemoryStore
from kinsun.observability.store import FakeTraceStore as FakeTraceStore
from kinsun.proactive.preferences import (
    FakeGreetingPreferenceStore as FakeGreetingPreferenceStore,
)
from kinsun.reports.reminders import FakeReminderLogStore as FakeReminderLogStore
from kinsun.reports.summaries import FakeConversationSummaryStore as FakeConversationSummaryStore
from kinsun.safety.events import FakeRiskEventStore as FakeRiskEventStore
from kinsun.scheduler.state import FakeScheduleStateStore as FakeScheduleStateStore
from kinsun.strategies.store import FakeStrategyStore as FakeStrategyStore


class FakeLongTermStore:
    def __init__(self, memories: list[MemoryItem] | None = None) -> None:
        self.added: list[tuple[str, list[Message], str]] = []
        self._memories = list(memories or [])

    def add(
        self, elder_id: str, messages: list[Message], *, provenance: str = "self_claimed"
    ) -> None:
        self.added.append((elder_id, list(messages), provenance))

    def search(self, elder_id: str, query: str, *, top_k: int = 5) -> list[MemoryItem]:
        return list(self._memories)
