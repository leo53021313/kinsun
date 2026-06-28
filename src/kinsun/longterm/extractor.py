"""長期記憶骨幹：一次抽取『事實＋情緒』。"""

from __future__ import annotations

import json
from dataclasses import dataclass

from kinsun.knowledge.facts import Fact, FactCategory, Provenance
from kinsun.llm import LLMClient, LLMError, Message

EXTRACT_SYSTEM_PROMPT = (
    "你是長者照護的長期記憶抽取器。從對話中同時抽取兩類內容："
    "(1) facts：穩定事實（個資/家庭/用藥/慢性病/事件），每筆 "
    "{category, content, provenance, confidence}；"
    "(2) episodes：有情緒意義的閒聊片段，每段一句簡短中文描述。"
    '只輸出 JSON 物件：{"facts": [...], "episodes": ["…"]}。'
    "facts.category 取 profile/family/medication/condition/event/other；"
    "facts.provenance 取 self_claimed（本人自述）或 inferred（推測）；"
    "健康宣稱若僅長者自述、未經確認，provenance 一律 self_claimed，不可當已確認。"
    "沒有的就用空陣列。只輸出 JSON。"
)


@dataclass(frozen=True)
class Consolidation:
    facts: list[Fact]
    episodes: list[str]


def _extract_json_object(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("找不到 JSON 物件")
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


def _parse_facts(session_id: str, items: object) -> list[Fact]:
    if not isinstance(items, list):
        return []
    facts: list[Fact] = []
    for item in items:
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


def _parse_episodes(items: object) -> list[str]:
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, str) and item]


def _parse_consolidation(session_id: str, raw: str) -> Consolidation:
    try:
        data = json.loads(_extract_json_object(raw))
    except (json.JSONDecodeError, ValueError):
        return Consolidation([], [])
    if not isinstance(data, dict):
        return Consolidation([], [])
    return Consolidation(
        _parse_facts(session_id, data.get("facts")),
        _parse_episodes(data.get("episodes")),
    )


class ConsolidationExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def extract(self, session_id: str, messages: list[Message]) -> Consolidation:
        if not messages:
            return Consolidation([], [])
        transcript = "\n".join(f"{m.role}: {m.text}" for m in messages)
        try:
            raw = self._llm.generate(
                system_prompt=EXTRACT_SYSTEM_PROMPT,
                messages=[Message("user", transcript)],
            )
        except LLMError:
            return Consolidation([], [])
        return _parse_consolidation(session_id, raw)
