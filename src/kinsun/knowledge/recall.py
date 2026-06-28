"""把已知事實格式化、供 agent 注入。"""

from __future__ import annotations

from kinsun.knowledge.facts import Fact, FactCategory, Provenance
from kinsun.knowledge.store import FactStore

_CATEGORY_ZH = {
    FactCategory.PROFILE: "個資",
    FactCategory.FAMILY: "家庭",
    FactCategory.MEDICATION: "用藥",
    FactCategory.CONDITION: "慢性病",
    FactCategory.EVENT: "事件",
    FactCategory.OTHER: "其他",
}
_PROVENANCE_ZH = {
    Provenance.SELF_CLAIMED: "長者自述",
    Provenance.INFERRED: "推測",
    Provenance.FAMILY_CONFIRMED: "家屬確認",
}


def format_facts_for_prompt(facts: list[Fact]) -> str:
    if not facts:
        return ""
    lines = [
        f"- [{_CATEGORY_ZH[f.category]}] {f.content}（{_PROVENANCE_ZH[f.provenance]}）"
        for f in facts
    ]
    return (
        "\n以下是你已知關於這位長者的資訊（部分為長者自述、未必經確認，"
        "請勿當成醫療診斷）：\n" + "\n".join(lines)
    )


class KnowledgeRecaller:
    def __init__(self, store: FactStore) -> None:
        self._store = store

    def recall(self, session_id: str) -> str:
        try:
            facts = self._store.all_for(session_id)
        except Exception:  # noqa: BLE001 - 記憶壞掉不可中斷對話
            return ""
        return format_facts_for_prompt(facts)
