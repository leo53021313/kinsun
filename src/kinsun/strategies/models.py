"""策略記憶（守則）的資料模型：金孫從互動中學到的「這位長輩的相處之道」。"""

from __future__ import annotations

from dataclasses import dataclass

# 守則分類白名單：反思只准產出這四類；不在此列者一律丟棄（見 policy.py）。
# 這是安全設計的一環——用藥、就醫、危急判斷永遠不是可學習的對象。
STRATEGY_CATEGORY_ADDRESS = "address"  # 稱呼：不愛被叫阿婆
STRATEGY_CATEGORY_TONE = "tone"  # 語氣：講太長會沒反應
STRATEGY_CATEGORY_ROUTINE = "routine"  # 作息：早上八點還在睡
STRATEGY_CATEGORY_TOPIC = "topic"  # 話題：不愛聊孫子
STRATEGY_CATEGORIES = (
    STRATEGY_CATEGORY_ADDRESS,
    STRATEGY_CATEGORY_TONE,
    STRATEGY_CATEGORY_ROUTINE,
    STRATEGY_CATEGORY_TOPIC,
)

# 守則自動生效（無人審佇列），故無 pending 狀態。
STRATEGY_STATUS_ADOPTED = "adopted"  # 生效中，會注入 system prompt
STRATEGY_STATUS_REVOKED = "revoked"  # 人工於後台撤銷
STRATEGY_STATUS_SUPERSEDED = "superseded"  # 被新守則取代
STRATEGY_STATUSES = (
    STRATEGY_STATUS_ADOPTED,
    STRATEGY_STATUS_REVOKED,
    STRATEGY_STATUS_SUPERSEDED,
)


@dataclass(frozen=True)
class Strategy:
    strategy_id: str
    elder_id: str
    content: str
    category: str  # ∈ STRATEGY_CATEGORIES
    evidence: str  # 反思當下引用的證據（後台檢視用）
    observed_days: int  # 此模式在過去幾天中出現過（證據門檻）
    status: str  # ∈ STRATEGY_STATUSES
    supersedes_strategy_id: str | None
    created_at: float
    revoked_at: float | None
