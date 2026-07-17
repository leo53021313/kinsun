"""Care Agent 樞紐：注入長期記憶情境 + 載入今日記憶 → 呼叫 LLM → 寫回。"""

from __future__ import annotations

from dataclasses import dataclass

from kinsun.llm import LLMClient, Message, ToolResult
from kinsun.memory.models import FactSection, InjectedContext, format_injected_context
from kinsun.memory.recall import SessionMemory
from kinsun.turn_context import elder_utterance


@dataclass(frozen=True)
class Recall:
    """她上次開口那天的對話摘要 ＋ 那天距今幾天（0＝今天稍早、1＝昨天）。

    days_ago 非帶不可：主動推播可能在她沉默多日後才發（失聯關心的門檻就是 2 天），
    此時摘要講的是好幾天前的事。真 Gemini 探針（scripts/recall_probe.py）實測：
    不講幾天前，模型會把舊摘要當成剛發生的事，說出「你好久沒找我聊天了……孫子
    這週末要來」這種自相矛盾的話。
    """

    content: str
    days_ago: int


def _recall_title(days_ago: int) -> str:
    """摘要段的段首（FactSection 慣例：title 自帶前後換行）。

    摘要是寫給家屬看的第三人稱敘述（「阿嬤今天心情不錯，聊到……」），直接貼進
    prompt 有被複述成「根據記錄，您昨天心情不錯」的風險，故明講「不必逐字複述」。
    """
    when = {0: "今天稍早", 1: "昨天"}.get(days_ago, f"{days_ago} 天前")
    return (
        f"\n以下是她{when}跟你聊天的狀況（系統摘要，不必逐字複述）。"
        f"可以順著裡面的事開話題，例如問問後來怎麼樣了；但那是{when}的事，"
        "別當成現在還在發生：\n"
    )


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
    # 地點三句（spec 2026-07-17）：三種情形各一句，缺一不可。第一句消滅「每次都反問」
    # （本功能的目的），第二句擋 anchoring（本功能最大的坑——位置每輪無條件進 prompt，
    # 模型容易看到「他在台南」就順手查台南），第三句保住沒有位置時的現行行為。
    "情境有時會附上長輩手機回報的目前位置。那是參考，不是答案——他問到的地點不一定是他人在的地方。"
    "他明確在問所在地的天氣，就直接用那個地點，不要多問；"
    "他提到要去別的地方（例如等下要去哪裡吃飯），就問清楚是哪裡，不可拿他目前的位置去查。"
    "情境沒有附位置時，一律先問，不要自己猜。"
    "長輩問時事或生活資訊、或轉述可疑訊息（疑似謠言、詐騙）時，用 web_search 工具查證；"
    "衛教問題一律先用 health_education_rag，它查不到才用 web_search。"
    "引用查到的內容要口語帶一句來源，例如「衛福部網站說」「查核中心說這是假的」，"
    "絕不唸出網址；查不到就保守回覆、建議長輩問家人或醫師，不可自行編答案。"
    "你是 AI，不要假裝是真人或家人；避免讓長者過度依賴你，適度鼓勵他與家人和現實生活互動。"
    "若長者陳述前後不一或可能記錯，不要爭辯，溫和回應即可。"
)

_PROACTIVE_DIRECTIVE = (
    "（系統提示，非長者發話）請主動關心長者：{intent}。用一句溫暖、口語、簡短的話開啟對話。"
)

# 有 recall 時補在任務描述後面（spec 2026-07-17）。
# 為什麼不寫進段首而要動任務：真 Gemini 實測四輪，想念推播**穩定**不理會摘要——
# 它的 intent（「主動表達想念與關心」）本身就是一個做得完的任務，模型做完就停，
# 段首怎麼寫都推不動。早安那條會用摘要是因為 intent 有「關心長者今天的狀況」，
# 字面對上了段首的「跟你聊天的狀況」。故槓桿在任務，不在情境。
# 條件式附加（recall=None 時完全不出現）是安全關鍵：無條件講「上次聊的事」會讓
# 沒有摘要的長輩被憑空編一段——實測顯示現況（無摘要時）不會編，不可回頭破壞它。
_PROACTIVE_RECALL_DIRECTIVE = (
    "順著上面她上次聊天的狀況，關心那件事後來怎麼樣了，不要只講泛泛的問候。"
)

# 統一回退話術（✅ 庚-37）：管線失敗與 LLM 空回覆共用；inbound.FALLBACK_PROMPT 為別名。
FALLBACK_REPLY = "金孫剛剛沒聽清楚，您可以再說一次嗎？"


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

    def _envelope(self, elder_id: str, query: str) -> tuple[str, list[Message]]:
        ctx = self._session.assemble(elder_id, query)
        return SYSTEM_PROMPT + ctx.system_suffix, ctx.history

    def handle(self, elder_id: str, user_text: str) -> str:
        system_prompt, history = self._envelope(elder_id, user_text)
        user_msg = Message("user", user_text)
        base = [*history, user_msg]
        if self._tools is None:
            reply = self._llm.generate(system_prompt=system_prompt, messages=base)
        else:
            # 把長輩的原話提供給工具（✅ spec 2026-07-17-天氣地點正確性）：天氣工具
            # 靠它分辨「長輩說的地點」與「模型自己猜的」。實測顯示模型不知道地點時
            # 會猜「台北市」去呼叫，而提示詞擋不住——那道防線的上游就在這裡。
            with elder_utterance(user_text):
                reply = self._run_tool_loop(system_prompt, base)
        self._session.record_turn(elder_id, user_msg, Message("assistant", reply))
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
        # 末輪修復（✅ 庚-35／A-14）：迭代上限用盡但工具結果已在手——再讓模型
        # 消化一次產出文字，不把成功的工具工作丟掉；仍堅持要工具（無文字）才回退。
        turn = self._llm.generate_tool_turn(
            system_prompt=system_prompt,
            messages=base,
            tools=self._tools.specs(),
            tool_results=results,
        )
        return turn.text or FALLBACK_REPLY

    def proactive(self, elder_id: str, intent: str, *, recall: Recall | None = None) -> str:
        """主動開場。recall＝她上次開口那天的摘要（spec 2026-07-17-主動問候接續昨天話題）。

        recall 一物三用：當長期記憶的檢索關鍵字、直接注入給模型看、並讓任務描述
        多一句追問指示（三者缺一，實測都推不動模型——見 spec）。
        - 當關鍵字：intent 是每天每位長輩都一樣的字串，拿它做語意檢索等於每天用
          同一把萬用鑰匙開所有人的門，撈回的與她上次講什麼無關。
        - 也直接給看：檢索終究是機率，關鍵字對了也不保證撈得回來；摘要既已在手，
          直接注入才能讓「記得上次聊什麼」是確定的。
        recall=None（她從沒開口／那天沒摘要／讀取失敗）＝一字不差維持本功能之前
        的行為。
        """
        system_prompt, history = self._envelope(elder_id, recall.content if recall else intent)
        if recall:
            # 重用既有的事實段排版，不另立 prompt 拼裝路徑。
            system_prompt += format_injected_context(
                InjectedContext(
                    sections=[
                        FactSection(title=_recall_title(recall.days_ago), items=[recall.content])
                    ]
                )
            )
        task = _PROACTIVE_DIRECTIVE.format(intent=intent)
        if recall:
            task += _PROACTIVE_RECALL_DIRECTIVE
        directive = Message("user", task)
        reply = self._llm.generate(system_prompt=system_prompt, messages=[*history, directive])
        # 留存的記憶帶主動關懷標記（✅ D-39 丙-8）：隔日 recall 看得懂這輪是系統
        # 主動開場，不是長輩憑空收到回覆；送給長輩的 reply 本身不帶標記。
        self._session.record_turn(elder_id, Message("assistant", f"【主動關懷｜{intent}】{reply}"))
        return reply
