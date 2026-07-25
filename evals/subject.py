"""受測系統（system under test）：把「一句話進、一句回覆出」組裝成單一入口。

Opik 實驗（`experiments/prompt_injection.py`）與 promptfoo 紅隊（`redteam/provider.py`）
都打同一個對象，故組裝只寫一次——兩邊各寫一份，遲早會分岔成「量的不是同一個東西」。

組裝的是**真的 `CareAgent`**（真 `SYSTEM_PROMPT` ＋出站 `_speakable()` 打撈），因為那
兩道正是要量的防線；換成簡化 prompt 等於量了一個不會上線的東西。但**不碰 DB**：短期
記憶用 `FakeMemoryStore`、長期記憶用本檔空實作、`tools=None`——注入防禦與記憶、工具
無關，砍掉這些依賴不影響量測對象，卻讓評測可在任何一台開發機離線跑。

濫用審核依 `SAFETY_MODERATION_ENABLED` 決定套不套，套法與 `pipeline._process_transcribed`
一致（判違規→取 `reply_for(category)`，否則進 agent）。⚠️ 兩邊若日後分岔，`test_pipeline`
的攔截測試會先炸——那裡才是正式路徑的真相來源，本檔只是評測用的最小重現。
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from kinsun import tracing
from kinsun.agent import CareAgent
from kinsun.llm import Message, build_gemini_for
from kinsun.memory.longterm.store import MemoryItem
from kinsun.memory.recall import SessionMemory
from kinsun.memory.shortterm import FakeMemoryStore
from kinsun.safety.moderation import AbuseModerator, LlmAbuseClassifier, reply_for


class NoLongTermStore:
    """LongTermStore 的空實作：評測不量長期記憶，檢索一律回空、寫入丟棄。"""

    def add(
        self,
        elder_id: str,
        messages: list[Message],
        *,
        provenance: str = "self_claimed",
        occurred_on: str | None = None,
    ) -> None:
        return None

    def search(self, elder_id: str, query: str, *, top_k: int | None = None) -> list[MemoryItem]:
        return []

    def list_for_elder(self, elder_id: str, *, limit: int = 50) -> list[MemoryItem]:
        return []


def elder_id_for(text: str) -> str:
    """每題一個穩定但互不相同的 elder_id，讓各題的短期記憶彼此隔離。

    `CareAgent.handle` 會把本輪寫回短期記憶，共用 elder_id 會讓第 1 題成功的綁架殘留
    在第 2 題的對話歷史裡，後面每一題都在被污染的狀態下受測，分數失真。
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def build_reply_fn(settings) -> Callable[[str], str]:
    """組出受測系統，回傳 `message -> reply` 的函式。呼叫端須自行先 `tracing.configure`。"""
    gemini = build_gemini_for(settings, settings.gemini_model, client_wrapper=tracing.wrap_genai)
    agent = CareAgent(gemini, SessionMemory(FakeMemoryStore(), NoLongTermStore()), tools=None)
    # 審核與危急分級共用 safety 模型，與 app.py 的接法一致。
    moderator = (
        AbuseModerator(
            LlmAbuseClassifier(
                build_gemini_for(
                    settings, settings.gemini_model_safety, client_wrapper=tracing.wrap_genai
                )
            ),
            min_confidence=settings.safety_moderation_min_confidence,
        )
        if settings.safety_moderation_enabled
        else None
    )

    def reply_to(message: str) -> str:
        if moderator is not None:
            moderation = moderator.moderate(message)
            if moderation.is_blocked:
                return reply_for(moderation.category)
        return agent.handle(elder_id_for(message), message)

    return reply_to
