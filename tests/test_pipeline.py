from kinsun.agent import CareAgent
from kinsun.llm import Message
from kinsun.pipeline import VoicePipeline
from kinsun.speech.asr import MockAsrClient
from kinsun.speech.tts import TextBubbleTts


class EchoLLM:
    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return f"你說的是：{messages[-1].text}"


def test_pipeline_runs_asr_agent_tts():
    pipeline = VoicePipeline(
        asr=MockAsrClient("阿公早安"),
        agent=CareAgent(EchoLLM()),
        tts=TextBubbleTts(),
    )
    result = pipeline.process(b"\x00\x01")
    assert result.text == "你說的是：阿公早安"
    assert result.audio is None
