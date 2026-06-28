from kinsun.agent import SYSTEM_PROMPT, CareAgent


class SpyLLM:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_text: str) -> str:
        self.calls.append((system_prompt, user_text))
        return "金孫回您：好的"


def test_handle_calls_llm_with_system_prompt_and_returns_reply():
    llm = SpyLLM()
    agent = CareAgent(llm)
    reply = agent.handle("我今天有點累")
    assert reply == "金孫回您：好的"
    assert llm.calls == [(SYSTEM_PROMPT, "我今天有點累")]
