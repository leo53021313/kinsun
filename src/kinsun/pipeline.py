"""語音管線：把 ASR、Agent、TTS 串成一次處理。"""

from __future__ import annotations

from kinsun.agent import CareAgent
from kinsun.speech.asr import ASRClient
from kinsun.speech.tts import TTSClient, TtsResult


class VoicePipeline:
    def __init__(self, *, asr: ASRClient, agent: CareAgent, tts: TTSClient) -> None:
        self._asr = asr
        self._agent = agent
        self._tts = tts

    def process(
        self, audio: bytes, *, session_id: str, content_type: str = "audio/m4a"
    ) -> TtsResult:
        user_text = self._asr.transcribe(audio, content_type=content_type)
        reply_text = self._agent.handle(session_id, user_text)
        return self._tts.synthesize(reply_text)
