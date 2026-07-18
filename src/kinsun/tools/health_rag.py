"""衛教 RAG 工具。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable

from kinsun.llm import ToolSpec
from kinsun.observability.store import TraceStore, safe_record
from kinsun.rag.service import HealthEducationRagService
from kinsun.tools.registry import ToolInvocationContext

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
        },
        "required": ["query"],
    },
)


def build_health_rag_handler(
    service: HealthEducationRagService,
    *,
    traces: TraceStore | None = None,
    timer: Callable[[], float] = time.monotonic,
) -> Callable[..., str]:
    def handler(
        args: dict,
        context: ToolInvocationContext | None = None,
    ) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return "請提供要查詢的衛教問題。"
        context = context or ToolInvocationContext()
        started = timer()
        answer = None
        error_message = ""
        try:
            answer = service.answer(query, has_risk_signal=context.has_risk_signal)
            payload = {
                "answer": answer.answer,
                "safety_level": answer.safety_level.value,
                "requires_safety_attention": answer.requires_safety_attention,
                "reason": answer.reason,
            }
            return json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            if traces is not None and context.trace_id:
                latency_ms = int((timer() - started) * 1000)
                hits = (
                    []
                    if answer is None
                    else [
                        {
                            "chunk_id": result.chunk.metadata.chunk_id,
                            "source_id": result.chunk.metadata.source_id,
                            "score": result.score,
                            "retrieval_method": result.retrieval_method,
                        }
                        for result in answer.evidence
                    ]
                )
                citations = (
                    []
                    if answer is None
                    else [
                        {
                            "source_id": citation.source_id,
                            "title": citation.title,
                            "publisher": citation.publisher,
                            "url": citation.url,
                            "chunk_id": citation.chunk_id,
                        }
                        for citation in answer.citations
                    ]
                )
                safe_record(
                    lambda: traces.record_rag(
                        trace_id=context.trace_id,
                        elder_id=context.elder_id,
                        query=query,
                        index_version=service.active_release_version(),
                        status=("error" if answer is None else answer.safety_level.value),
                        latency_ms=latency_ms,
                        safety_level=("error" if answer is None else answer.safety_level.value),
                        reason=error_message if answer is None else answer.reason,
                        hits=hits,
                        citations=citations,
                    )
                )

    return handler
