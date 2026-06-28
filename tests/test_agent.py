from kinsun.agent import CareAgent
from kinsun.llm import Message


class SpyLLM:
    def __init__(self) -> None:
        self.messages: list[Message] | None = None

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        self.messages = messages
        return "金孫回您：好的"


def test_handle_wraps_user_text_and_returns_reply():
    llm = SpyLLM()
    reply = CareAgent(llm).handle("我今天有點累")
    assert reply == "金孫回您：好的"
    assert llm.messages == [Message("user", "我今天有點累")]
