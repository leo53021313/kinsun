"""抽取情緒／閒聊片段（fail-safe）。"""

from __future__ import annotations

import json

from kinsun.llm import LLMClient, LLMError, Message

EXTRACT_SYSTEM_PROMPT = (
    "你是長者照護的情緒記憶抽取器。從對話中抽取『有情緒意義的閒聊片段』"
    "（思念、開心、孤單、擔心、興趣嗜好等），每段用一句簡短中文描述。"
    '只輸出 JSON 字串陣列：["…", "…"]。沒有可抽取的就回 []。只輸出 JSON。'
)


def _extract_json_array(raw: str) -> str:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("找不到 JSON 陣列")
    return raw[start : end + 1]


def _parse_episodes(raw: str) -> list[str]:
    try:
        data = json.loads(_extract_json_array(raw))
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str) and item]


class EpisodeExtractor:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def extract(self, messages: list[Message]) -> list[str]:
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
        return _parse_episodes(raw)
