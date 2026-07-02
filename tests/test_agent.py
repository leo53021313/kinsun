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


class SpyMemory:
    def __init__(self, history: list[Message] | None = None) -> None:
        self._history = history or []
        self.appended: list[tuple[str, Message]] = []

    def recent(self, line_user_id: str) -> list[Message]:
        return list(self._history)

    def append(self, line_user_id: str, message: Message) -> None:
        self.appended.append((line_user_id, message))


class SpyContext:
    def __init__(self, text: str = "") -> None:
        self._text = text

    def recall(self, line_user_id: str, user_text: str) -> str:
        return self._text


def test_handle_includes_history_and_writes_back():
    llm = SpyLLM()
    memory = SpyMemory([Message("user", "早安"), Message("assistant", "阿公早")])
    agent = CareAgent(llm, memory, SpyContext(""))

    reply = agent.handle("u1", "我今天有點累")

    assert reply == "金孫回您：好的"
    assert llm.system_prompt == SYSTEM_PROMPT
    assert llm.messages == [
        Message("user", "早安"),
        Message("assistant", "阿公早"),
        Message("user", "我今天有點累"),
    ]
    assert memory.appended == [
        ("u1", Message("user", "我今天有點累")),
        ("u1", Message("assistant", "金孫回您：好的")),
    ]


def test_handle_injects_known_facts_into_system_prompt():
    llm = SpyLLM()
    agent = CareAgent(llm, SpyMemory(), SpyContext("\n已知：高血壓（長者自述）"))
    agent.handle("u1", "嗨")
    assert llm.system_prompt == SYSTEM_PROMPT + "\n已知：高血壓（長者自述）"


def test_proactive_composes_with_memory_and_writes_back():
    llm = SpyLLM()
    memory = SpyMemory()
    agent = CareAgent(llm, memory, SpyContext("【記憶】"))

    reply = agent.proactive("u1", "早安問候")

    assert reply == "金孫回您：好的"
    assert llm.system_prompt == SYSTEM_PROMPT + "【記憶】"
    assert "早安問候" in llm.messages[-1].text
    assert memory.appended == [("u1", Message("assistant", "金孫回您：好的"))]


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
    memory = SpyMemory()
    agent = CareAgent(llm, memory, SpyContext(""), tools=_registry_with_weather())
    reply = agent.handle("u1", "今天台北天氣？")
    assert reply == "台北今天晴，記得多喝水"
    assert memory.appended == [
        ("u1", Message("user", "今天台北天氣？")),
        ("u1", Message("assistant", "台北今天晴，記得多喝水")),
    ]
    assert llm.calls == [0, 1]  # 第二輪帶入 1 筆 tool_result


def test_tool_loop_caps_iterations():
    always_tool = ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {})])
    llm = ScriptedToolLLM([always_tool, always_tool, always_tool])
    agent = CareAgent(
        llm, SpyMemory(), SpyContext(""), tools=_registry_with_weather(), max_tool_iters=3
    )
    reply = agent.handle("u1", "天氣")
    assert reply == FALLBACK_REPLY
    assert len(llm.calls) == 3
