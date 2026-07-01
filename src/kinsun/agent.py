"""Care Agent 樞紐：注入長期記憶情境 + 載入今日記憶 → 呼叫 LLM → 寫回。"""

from __future__ import annotations

from kinsun.llm import LLMClient, Message, ToolResult
from kinsun.memory.store import MemoryStore
from kinsun.recall import MemoryContext

SYSTEM_PROMPT = (
    "你是「金孫」，一位溫暖、有耐心的台灣長輩陪伴助理。"
    "一律用台灣繁體中文、口語、簡短地回應，語氣像晚輩關心長輩。"
    "你不是醫師，絕不提供醫療診斷或用藥劑量建議；遇到健康疑慮，溫柔建議對方告訴家人或就醫。"
    "回答一般健康衛教時，必須先使用 health_education_rag 工具查詢可信來源；"
    "若工具回傳 unsupported 或 should_escalate_to_risk_engine，"
    "就照工具結果保守回覆，不可自行補醫療建議。"
    "你是 AI，不要假裝是真人或家人；避免讓長者過度依賴你，適度鼓勵他與家人和現實生活互動。"
    "若長者陳述前後不一或可能記錯，不要爭辯，溫和回應即可。"
)

_PROACTIVE_DIRECTIVE = (
    "（系統提示，非長者發話）請主動關心長者：{intent}。用一句溫暖、口語、簡短的話開啟對話。"
)

FALLBACK_REPLY = "金孫剛剛想了一下沒講清楚，您可以再說一次嗎？"


class CareAgent:
    def __init__(
        self,
        llm: LLMClient,
        memory: MemoryStore,
        context: MemoryContext,
        *,
        tools=None,
        max_tool_iters: int = 3,
    ) -> None:
        self._llm = llm
        self._memory = memory
        self._context = context
        self._tools = tools
        self._max_tool_iters = max_tool_iters

    def handle(self, session_id: str, user_text: str) -> str:
        system_prompt = SYSTEM_PROMPT + self._context.recall(session_id, user_text)
        user_msg = Message("user", user_text)
        base = [*self._memory.recent(session_id), user_msg]
        if self._tools is None:
            reply = self._llm.generate(system_prompt=system_prompt, messages=base)
        else:
            reply = self._run_tool_loop(system_prompt, base)
        self._memory.append(session_id, user_msg)
        self._memory.append(session_id, Message("assistant", reply))
        return reply

    def _run_tool_loop(self, system_prompt: str, base: list[Message]) -> str:
        results: list[ToolResult] = []
        for _ in range(self._max_tool_iters):
            turn = self._llm.generate_tool_turn(
                system_prompt=system_prompt,
                messages=base,
                tools=self._tools.specs(),
                tool_results=results,
            )
            if not turn.tool_calls:
                return turn.text or FALLBACK_REPLY
            for call in turn.tool_calls:
                results.append(ToolResult(call, self._tools.dispatch(call.name, call.arguments)))
        return FALLBACK_REPLY

    def proactive(self, session_id: str, intent: str) -> str:
        system_prompt = SYSTEM_PROMPT + self._context.recall(session_id, intent)
        history = self._memory.recent(session_id)
        directive = Message("user", _PROACTIVE_DIRECTIVE.format(intent=intent))
        reply = self._llm.generate(system_prompt=system_prompt, messages=[*history, directive])
        self._memory.append(session_id, Message("assistant", reply))
        return reply
