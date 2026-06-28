"""衛教 RAG 回答安全閘門。"""

from __future__ import annotations

from kinsun.rag.citation import assemble_citations
from kinsun.rag.schemas import RagAnswer, SafetyLevel, SearchResult

_UNSUPPORTED_ANSWER = (
    "目前查不到足夠可信的衛教資料，我不能亂給健康建議。"
    "請詢問醫師、護理師或藥師；若是緊急不舒服，請立即聯絡家人或撥 119。"
)

_URGENT_ANSWER = (
    "這個情況可能需要先由風險偵測與升級流程處理。"
    "我不會用衛教資料替您判斷病情，請先通知家人；若很不舒服請撥 119。"
)

_MEDICAL_ACTION_TERMS = (
    "診斷",
    "是不是",
    "能不能停藥",
    "可以停藥",
    "停藥",
    "調藥",
    "加藥",
    "藥量",
    "急診",
)


class AnswerPolicy:
    def build_answer(
        self,
        query: str,
        evidence: tuple[SearchResult, ...],
        *,
        has_risk_signal: bool = False,
    ) -> RagAnswer:
        if has_risk_signal:
            return RagAnswer(
                answer=_URGENT_ANSWER,
                safety_level=SafetyLevel.URGENT,
                citations=(),
                should_escalate_to_risk_engine=True,
                reason="偵測到需由 Risk Engine 處理的風險訊號。",
            )
        if _is_medical_action_request(query):
            return RagAnswer(
                answer=_UNSUPPORTED_ANSWER,
                safety_level=SafetyLevel.UNSUPPORTED,
                citations=(),
                should_escalate_to_risk_engine=True,
                reason="使用者要求診斷、急症判斷或用藥決策。",
            )
        if not evidence:
            return RagAnswer(
                answer=_UNSUPPORTED_ANSWER,
                safety_level=SafetyLevel.UNSUPPORTED,
                citations=(),
                should_escalate_to_risk_engine=False,
                reason="沒有足夠可信來源可支撐回答。",
            )

        citations = assemble_citations(evidence)
        if not citations:
            return RagAnswer(
                answer=_UNSUPPORTED_ANSWER,
                safety_level=SafetyLevel.UNSUPPORTED,
                citations=(),
                should_escalate_to_risk_engine=False,
                reason="無法組出完整 citation。",
            )

        snippets = " ".join(_compact(result.chunk.text) for result in evidence[:2])
        answer = f"我查到的衛教資料重點是：{snippets}"
        return RagAnswer(
            answer=answer,
            safety_level=SafetyLevel.NORMAL,
            citations=citations,
            should_escalate_to_risk_engine=False,
            reason="已找到可信來源並完成 citation。",
        )


def _is_medical_action_request(query: str) -> bool:
    return any(term in query for term in _MEDICAL_ACTION_TERMS)


def _compact(text: str, *, max_chars: int = 120) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars]}..."
