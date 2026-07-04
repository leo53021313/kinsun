"""Care Agent 樞紐：注入長期記憶情境 + 載入今日記憶 → 呼叫 LLM → 寫回。"""

from __future__ import annotations

from kinsun.llm import LLMClient, Message, ToolResult
from kinsun.memory.recall import SessionMemory

SYSTEM_PROMPT = (
    "你是「金孫」，一位溫暖、有耐心的台灣長輩陪伴助理。"
    "你的回覆會被合成成語音念給長輩聽，所以務必遵守："
    "（1）只用台灣繁體中文口語，像晚輩在跟阿公阿嬤講話；"
    "（2）非常簡短，最多兩三句、盡量控制在四十個字以內；"
    "（3）絕對不要用條列、標題、星號、括號補充或任何 Markdown 符號，只講白話短句；"
    "（4）不要主動自我介紹或羅列你會做什麼，除非長輩親口問你是誰；"
    "（5）結尾自然帶一句關心或反問，讓對話能接下去。"
    "你不是醫師，絕不提供醫療診斷或用藥劑量建議；遇到健康疑慮，溫柔建議對方告訴家人或就醫。"
    "回答一般健康衛教時，必須先使用 health_education_rag 工具查詢可信來源；"
    "若工具回傳 unsupported 或 should_escalate_to_risk_engine，"
    "就照工具結果保守回覆，不可自行補醫療建議。"
    "查天氣前若不知道長輩人在哪個城市，先親口問清楚，不要自己猜地點。"
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
        session: SessionMemory,
        *,
        tools=None,
        max_tool_iters: int = 3,
    ) -> None:
        self._llm = llm
        self._session = session
        self._tools = tools
        self._max_tool_iters = max_tool_iters

    def _envelope(self, line_user_id: str, query: str) -> tuple[str, list[Message]]:
        ctx = self._session.assemble(line_user_id, query)
        return SYSTEM_PROMPT + ctx.system_suffix, ctx.history

    def handle(self, line_user_id: str, user_text: str) -> str:
        system_prompt, history = self._envelope(line_user_id, user_text)
        user_msg = Message("user", user_text)
        base = [*history, user_msg]
        if self._tools is None:
            reply = self._llm.generate(system_prompt=system_prompt, messages=base)
        else:
            reply = self._run_tool_loop(system_prompt, base)
        self._session.record_turn(line_user_id, user_msg, Message("assistant", reply))
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

    def proactive(self, line_user_id: str, intent: str) -> str:
        system_prompt, history = self._envelope(line_user_id, intent)
        directive = Message("user", _PROACTIVE_DIRECTIVE.format(intent=intent))
        reply = self._llm.generate(system_prompt=system_prompt, messages=[*history, directive])
        self._session.record_turn(line_user_id, Message("assistant", reply))
        return reply
