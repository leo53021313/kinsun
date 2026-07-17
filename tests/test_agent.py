from kinsun.agent import FALLBACK_REPLY, SYSTEM_PROMPT, CareAgent
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

    def assemble(self, line_user_id: str, query: str) -> _Ctx:
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
