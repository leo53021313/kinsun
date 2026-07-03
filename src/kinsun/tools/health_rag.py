"""衛教 RAG 工具。"""

from __future__ import annotations

import json
from collections.abc import Callable

from kinsun.llm import ToolSpec
from kinsun.rag.service import HealthEducationRagService

HEALTH_RAG_SPEC = ToolSpec(
    name="health_education_rag",
    description=(
        "查詢可信衛教資料並回傳有 citation 的回答。"
        "只用於一般衛教；急症、診斷、停藥、調藥問題會回傳需升級。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "使用者的健康衛教問題"},
            "has_risk_signal": {
                "type": "boolean",
                "description": "若上游已判斷有急症或高風險訊號，設為 true",
            },
        },
        "required": ["query"],
    },
)


def build_health_rag_handler(service: HealthEducationRagService) -> Callable[[dict], str]:
    def handler(args: dict) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return "請提供要查詢的衛教問題。"
        answer = service.answer(query, has_risk_signal=bool(args.get("has_risk_signal")))
        payload = {
            "answer": answer.answer,
            "safety_level": answer.safety_level.value,
            "should_escalate_to_risk_engine": answer.should_escalate_to_risk_engine,
            "reason": answer.reason,
            "citations": [
                {
                    "source_id": citation.source_id,
                    "title": citation.title,
                    "publisher": citation.publisher,
                    "url": citation.url,
                    "chunk_id": citation.chunk_id,
                }
                for citation in answer.citations
            ],
        }
        return json.dumps(payload, ensure_ascii=False)

    return handler
