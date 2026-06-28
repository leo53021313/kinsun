from kinsun.agent import SYSTEM_PROMPT, CareAgent
from kinsun.llm import Message


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

    def recent(self, session_id: str) -> list[Message]:
        return list(self._history)

    def append(self, session_id: str, message: Message) -> None:
        self.appended.append((session_id, message))


def test_handle_includes_history_and_writes_back():
    llm = SpyLLM()
    memory = SpyMemory([Message("user", "早安"), Message("assistant", "阿公早")])
    agent = CareAgent(llm, memory)

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
