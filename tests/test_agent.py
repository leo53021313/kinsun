from kinsun.agent import FALLBACK_REPLY, SYSTEM_PROMPT, CareAgent, Recall
from kinsun.llm import Message, ToolCall, ToolSpec, ToolTurn
from kinsun.tools.registry import ToolRegistry


class SpyLLM:
    def __init__(self) -> None:
        self.system_prompt: str | None = None
        self.messages: list[Message] | None = None

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        self.system_prompt = system_prompt
        self.messages = messages
        return "金孫回您：好的"


class _Ctx:
    """SessionMemory.assemble 的替身回傳：只需 system_suffix ＋ history 兩個屬性。"""

    def __init__(self, system_suffix: str, history: list[Message]) -> None:
        self.system_suffix = system_suffix
        self.history = history


class SpySession:
    def __init__(self, system_suffix: str = "", history: list[Message] | None = None) -> None:
        self._suffix = system_suffix
        self._history = history or []
        self.recorded: list[tuple[str, tuple[Message, ...]]] = []
        self.queries: list[str] = []

    def assemble(self, line_user_id: str, query: str) -> _Ctx:
        self.queries.append(query)  # 檢索關鍵字是本次的受測對象，必須留痕
        return _Ctx(self._suffix, list(self._history))

    def record_turn(self, line_user_id: str, *messages: Message) -> None:
        self.recorded.append((line_user_id, messages))


def test_handle_includes_history_and_writes_back():
    llm = SpyLLM()
    session = SpySession(history=[Message("user", "早安"), Message("assistant", "阿公早")])
    agent = CareAgent(llm, session)

    reply = agent.handle("u1", "我今天有點累")

    assert reply == "金孫回您：好的"
    assert llm.system_prompt == SYSTEM_PROMPT
    assert llm.messages == [
        Message("user", "早安"),
        Message("assistant", "阿公早"),
        Message("user", "我今天有點累"),
    ]
    assert session.recorded == [
        ("u1", (Message("user", "我今天有點累"), Message("assistant", "金孫回您：好的"))),
    ]


def test_handle_injects_known_facts_into_system_prompt():
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession(system_suffix="\n已知：高血壓（長者自述）"))
    agent.handle("u1", "嗨")
    assert llm.system_prompt == SYSTEM_PROMPT + "\n已知：高血壓（長者自述）"


def test_proactive_composes_with_memory_and_writes_back():
    llm = SpyLLM()
    session = SpySession(system_suffix="【記憶】")
    agent = CareAgent(llm, session)

    reply = agent.proactive("u1", "早安問候")

    assert reply == "金孫回您：好的"
    assert llm.system_prompt == SYSTEM_PROMPT + "【記憶】"
    assert "早安問候" in llm.messages[-1].content
    # ✅ D-39（丙-8）：留存的記憶帶主動關懷標記——隔日 recall 不再看到憑空開場；
    # 回傳給長輩的 reply 本身不帶標記。
    assert session.recorded == [
        ("u1", (Message("assistant", "【主動關懷｜早安問候】金孫回您：好的"),))
    ]


def test_proactive_recalls_with_given_query_instead_of_intent():
    """檢索關鍵字改用昨天摘要（spec 2026-07-17-主動問候接續昨天話題）。

    拿 intent 去搜長期記憶，每天每位長輩都是同一句話比對向量，撈回的必然與她
    昨天講了什麼無關——問候於是收斂到 HEALTH_QUERY 撈出的健康罐頭。
    """
    session = SpySession()
    agent = CareAgent(SpyLLM(), session)

    agent.proactive("u1", "早安問候", recall=Recall("阿嬤心情不錯，聊到孫子週末要來看她", 1))

    assert session.queries == ["阿嬤心情不錯，聊到孫子週末要來看她"]


def test_proactive_falls_back_to_intent_without_recall():
    """昨天沒講話＝沒摘要：一字不差維持原行為，不可因此壞掉。"""
    session = SpySession()
    agent = CareAgent(SpyLLM(), session)

    agent.proactive("u1", "早安問候")

    assert session.queries == ["早安問候"]


def test_proactive_shows_recall_to_the_model():
    """檢索終究是機率；摘要既已在手上就直接給看，「記得昨天」才是確定的。"""
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession(system_suffix="【記憶】"))

    agent.proactive("u1", "早安問候", recall=Recall("阿嬤心情不錯，聊到孫子週末要來看她", 1))

    assert "阿嬤心情不錯，聊到孫子週末要來看她" in llm.system_prompt
    assert "【記憶】" in llm.system_prompt  # 不可取代既有注入情境，是相加


class ScriptedToolLLM:
    """依序回傳預設 ToolTurn；有工具時不應呼叫 generate。"""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def generate(self, *, system_prompt, messages):
        raise AssertionError("有工具時不應呼叫 generate")

    def generate_tool_turn(self, *, system_prompt, messages, tools, tool_results):
        self.calls.append(len(tool_results))
        return self._turns.pop(0)


def _registry_with_weather(output="台北今天晴 25°C"):
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="get_weather", description="天氣", parameters={"type": "object", "properties": {}}
        ),
        lambda args: output,
    )
    return reg


def test_handle_runs_tool_loop_then_returns_text():
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {"location": "台北"})]),
            ToolTurn(text="台北今天晴，記得多喝水", tool_calls=[]),
        ]
    )
    session = SpySession()
    agent = CareAgent(llm, session, tools=_registry_with_weather())
    reply = agent.handle("u1", "今天台北天氣？")
    assert reply == "台北今天晴，記得多喝水"
    assert session.recorded == [
        ("u1", (Message("user", "今天台北天氣？"), Message("assistant", "台北今天晴，記得多喝水"))),
    ]
    assert llm.calls == [0, 1]  # 第二輪帶入 1 筆 tool_result


def test_tool_loop_last_round_digests_results_instead_of_fallback():
    """✅ 庚-35（A-14）：迭代上限用盡但工具已成功執行——末輪多一次消化呼叫，
    模型基於工具結果產出文字，不再把成功的工具工作丟掉直接回退。"""
    always_tool = ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {})])
    digest = ToolTurn(text="查到台北是晴天喔", tool_calls=[])
    llm = ScriptedToolLLM([always_tool, always_tool, always_tool, digest])
    agent = CareAgent(llm, SpySession(), tools=_registry_with_weather(), max_tool_iters=3)
    reply = agent.handle("u1", "天氣")
    assert reply == "查到台北是晴天喔"
    assert len(llm.calls) == 4  # 3 輪工具＋1 輪消化
    assert llm.calls[-1] == 3  # 消化輪帶著全部 3 筆工具結果


def test_tool_loop_falls_back_when_digest_still_wants_tools():
    """消化輪模型仍堅持呼叫工具（無文字）→ 才回退。"""
    always_tool = ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {})])
    llm = ScriptedToolLLM([always_tool] * 4)
    agent = CareAgent(llm, SpySession(), tools=_registry_with_weather(), max_tool_iters=3)
    reply = agent.handle("u1", "天氣")
    assert reply == FALLBACK_REPLY


def test_system_prompt_frames_location_as_hint_not_answer():
    """⚠️ 回歸防線，非行為驗證。

    假 LLM 不會推理，「模型不拿所在地去查別處」在此測不出來——那需要真的
    Gemini，屬人工複驗（見 plan Task 7）。本測試只確保這三句話沒被刪改：
    第一句消滅「每次都反問」，第二句擋 anchoring，第三句保住沒位置時的行為。
    """
    assert "他明確在問所在地的天氣，就直接用那個地點，不要多問" in SYSTEM_PROMPT
    assert "不可拿他目前的位置去查" in SYSTEM_PROMPT
    assert "情境沒有附位置時，一律先問" in SYSTEM_PROMPT


def test_handle_exposes_utterance_to_tools():
    """⚠️ 天氣工具靠這個分辨「長輩說的地點」與「模型自己猜的」。

    實測（真 Gemini）：模型不知道長輩在哪時會猜「台北市」去呼叫工具，工具照查
    照回，金孫就把台北的天氣報給別處的長輩。提示詞擋不住——這條是結構性防線的
    上游，斷了它，防線就形同虛設而且沒有東西會紅。
    """
    from kinsun.turn_context import current_utterance

    seen: list[str] = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="spy", description="", parameters={"type": "object", "properties": {}}),
        lambda _args: seen.append(current_utterance()) or "ok",
    )
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("spy", {})]),
            ToolTurn(text="好喔", tool_calls=[]),
        ]
    )

    CareAgent(llm, SpySession(), tools=registry).handle("e1", "我在台南，今天天氣如何？")

    assert seen == ["我在台南，今天天氣如何？"]


def test_proactive_does_not_leak_previous_utterance():
    """主動關懷沒有長輩原話——不可讓上一輪的話殘留在 context 裡。"""
    from kinsun.turn_context import current_utterance

    CareAgent(SpyLLM(), SpySession()).handle("e1", "我在台南")

    assert current_utterance() == ""


def test_proactive_tells_the_model_how_long_ago_they_spoke():
    """幾天前必須明講（spec 2026-07-17）：她上次開口可能是昨天，也可能是九天前。

    真 Gemini 探針顯示，不講就會出現「你好久沒找我聊天了……孫子這週末要來」
    這種自相矛盾的話——模型把舊摘要當成剛剛發生的事。
    """
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession())

    agent.proactive("u1", "想念", recall=Recall("阿嬤聊到孫子要來", 5))

    assert "5 天前" in llm.system_prompt


def test_proactive_says_yesterday_rather_than_one_day_ago():
    """「1 天前」是機器話；長輩聽到的是金孫的口語，講「昨天」。"""
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession())

    agent.proactive("u1", "早安問候", recall=Recall("阿嬤聊到孫子要來", 1))

    assert "昨天" in llm.system_prompt
    assert "1 天前" not in llm.system_prompt


def test_proactive_asks_the_model_to_follow_up_on_the_recall():
    """有 recall 時，任務描述要明著叫它追問那件事（spec 2026-07-17）。

    真 Gemini 實測：光把摘要放進情境不夠——想念推播的 intent（「主動表達想念與
    關心」）本身是個做得完的任務，模型做完就停，連測四輪都不理會摘要。改動任務
    描述後才追問「孫子有來看妳嗎」。段首措辭怎麼改都推不動，槓桿在這裡。
    """
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession())

    agent.proactive("u1", "想念", recall=Recall("阿嬤聊到孫子要來", 5))

    assert "後來怎麼樣了" in llm.messages[-1].content


def test_proactive_never_asks_to_follow_up_without_a_recall():
    """⚠️ 安全線：沒摘要就絕不可提「上次聊的事」——沒有的東西，模型會編一個。

    實測現況（無摘要時）金孫只講泛泛的問候、不編故事；這條測試防的是有人把上面
    那句追問指示改成無條件附加，一句之差就會讓沒講過話的長輩收到憑空的回憶。
    """
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession())

    agent.proactive("u1", "想念")

    assert "後來怎麼樣了" not in llm.messages[-1].content
    assert "上次" not in llm.messages[-1].content
