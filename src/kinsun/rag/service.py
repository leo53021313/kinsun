"""衛教 RAG 服務入口：檢索 → 安全閘門 → grounded answer。"""

from __future__ import annotations

from kinsun.llm import LLMClient, Message
from kinsun.rag.answer_policy import AnswerPolicy
from kinsun.rag.schemas import RagAnswer, SafetyLevel, SearchResult

_GROUNDING_PROMPT = (
    "你是 KinSun 衛教 RAG 的回答改寫器。"
    "只能根據提供的 evidence 改寫，不可新增 evidence 沒有的醫療內容。"
    "一律使用台灣繁體中文、短句、長輩聽得懂的口語。"
    "不可診斷、不可建議停藥或調藥、不可判斷是否急診。"
)


class HealthEducationRagService:
    def __init__(
        self,
        retriever,
        *,
        answer_policy: AnswerPolicy | None = None,
        llm: LLMClient | None = None,
        top_k: int = 5,
    ) -> None:
        self._retriever = retriever
        self._policy = answer_policy or AnswerPolicy()
        self._llm = llm
        self._top_k = top_k

    def answer(self, query: str, *, has_risk_signal: bool = False) -> RagAnswer:
        evidence: tuple[SearchResult, ...] = ()
        if not has_risk_signal:
            evidence = self._retriever.retrieve(query, top_k=self._top_k)
        answer = self._policy.build_answer(query, evidence, has_risk_signal=has_risk_signal)
        if self._llm is None or answer.safety_level != SafetyLevel.NORMAL:
            return answer
        rewritten = self._rewrite_with_llm(query, evidence, answer.answer)
        return RagAnswer(
            answer=rewritten,
            safety_level=answer.safety_level,
            citations=answer.citations,
            should_escalate_to_risk_engine=answer.should_escalate_to_risk_engine,
            reason=answer.reason,
        )

    def _rewrite_with_llm(
        self,
        query: str,
        evidence: tuple[SearchResult, ...],
        fallback_answer: str,
    ) -> str:
        evidence_text = "\n".join(
            f"[{index}] {result.chunk.metadata.title}｜{result.chunk.metadata.publisher}｜"
            f"{result.chunk.text}"
            for index, result in enumerate(evidence[: self._top_k], start=1)
        )
        prompt = (
            f"使用者問題：{query}\n\n"
            f"Evidence：\n{evidence_text}\n\n"
            "請用 2 到 4 句回答，最後不要自行編來源，citation 由系統附上。"
        )
        try:
            return self._llm.generate(
                system_prompt=_GROUNDING_PROMPT,
                messages=[Message("user", prompt)],
            )
        except Exception:  # noqa: BLE001 - LLM 改寫失敗時保留 extractive answer
            return fallback_answer
