"""語音管線：把 ASR、偵測、Agent、TTS 串成一次處理。"""

from __future__ import annotations

from kinsun.agent import CareAgent
from kinsun.safety.detector import RiskDetector
from kinsun.safety.notifier import Notifier
from kinsun.safety.tiers import RiskTier
from kinsun.speech.asr import ASRClient
from kinsun.speech.tts import TTSClient, TtsResult


class VoicePipeline:
    def __init__(
        self,
        *,
        asr: ASRClient,
        agent: CareAgent,
        tts: TTSClient,
        detector: RiskDetector,
        notifier: Notifier,
    ) -> None:
        self._asr = asr
        self._agent = agent
        self._tts = tts
        self._detector = detector
        self._notifier = notifier

    def process(
        self, audio: bytes, *, session_id: str, content_type: str = "audio/m4a"
    ) -> TtsResult:
        user_text = self._asr.transcribe(audio, content_type=content_type)
        assessment = self._detector.assess(user_text)
        reply_text = self._agent.handle(session_id, user_text)
        if assessment.tier >= RiskTier.L2:
            self._notifier.notify(session_id, assessment)
        return self._tts.synthesize(reply_text)
