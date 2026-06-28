"""從對話抽取結構化事實（fail-safe）。"""

from __future__ import annotations

import json

from kinsun.knowledge.facts import Fact, FactCategory, Provenance
from kinsun.llm import LLMClient, LLMError, Message

EXTRACT_SYSTEM_PROMPT = (
    "你是長者照護的事實抽取器。從對話中抽取關於這位長者的『穩定事實』"
    "（個資、家庭、用藥、慢性病、事件）。"
    '只輸出 JSON 陣列：[{"category": "...", "content": "...", '
    '"provenance": "...", "confidence": 0-1}]。'
    "category 取 profile/family/medication/condition/event/other；"
    "provenance 取 self_claimed（本人自述）或 inferred（推測）。"
    "重要：健康宣稱若只是長者自述、未經確認，provenance 一律 self_claimed，"
    "不要當成已確認的事實。沒有可抽取的事實就回 []。只輸出 JSON。"
)


def _extract_json_array(raw: str) -> str:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("找不到 JSON 陣列")
    return raw[start : end + 1]


def _to_category(value: object) -> FactCategory:
    try:
        return FactCategory(value)
    except ValueError:
        return FactCategory.OTHER


def _to_provenance(value: object) -> Provenance:
    try:
        return Provenance(value)
    except ValueError:
        return Provenance.INFERRED


def _clamp(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _parse_facts(session_id: str, raw: str) -> list[Fact]:
    try:
        data = json.loads(_extract_json_array(raw))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    facts: list[Fact] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content:
            continue
        facts.append(
            Fact(
                session_id,
                _to_category(item.get("category")),
                content,
                _to_provenance(item.get("provenance")),
                _clamp(item.get("confidence")),
            )
        )
    return facts


class FactExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def extract(self, session_id: str, messages: list[Message]) -> list[Fact]:
        if not messages:
            return []
        transcript = "\n".join(f"{m.role}: {m.text}" for m in messages)
        try:
            raw = self._llm.generate(
                system_prompt=EXTRACT_SYSTEM_PROMPT,
                messages=[Message("user", transcript)],
            )
        except LLMError:
            return []
        return _parse_facts(session_id, raw)
