"""語音管線：把 ASR、偵測、Agent、TTS 串成一次處理。"""

from __future__ import annotations

import logging
from dataclasses import replace

from kinsun.agent import CareAgent
from kinsun.safety.detector import RiskDetector
from kinsun.safety.events import RiskEventStore
from kinsun.safety.notifier import Notifier
from kinsun.safety.tiers import RiskTier
from kinsun.speech.asr import ASRClient
from kinsun.speech.tts import TTSClient, TTSError, TtsResult

logger = logging.getLogger("kinsun.pipeline")


class VoicePipeline:
    def __init__(
        self,
        *,
        asr: ASRClient,
        agent: CareAgent,
        tts: TTSClient,
        detector: RiskDetector,
        notifier: Notifier,
        risk_events: RiskEventStore,
    ) -> None:
        self._asr = asr
        self._agent = agent
        self._tts = tts
        self._detector = detector
        self._notifier = notifier
        self._risk_events = risk_events

    def process(
        self, audio: bytes, *, line_user_id: str, content_type: str = "audio/m4a"
    ) -> TtsResult:
        user_text = self._asr.transcribe(audio, content_type=content_type)
        assessment = self._detector.assess(user_text)
        # 危急通知須獨立於回覆生成：先落庫＋通知家屬，才產生回覆。
        # 否則 agent 生成回覆時若丟例外，會讓已偵測到的危急漏通知。
        if assessment.tier >= RiskTier.L2:
            try:
                self._risk_events.record(line_user_id, assessment)
            except Exception:  # noqa: BLE001 - 落庫失敗不可中斷對話
                logger.warning("危急事件落庫失敗")
            self._notifier.notify(line_user_id, assessment)
        reply_text = self._agent.handle(line_user_id, user_text)
        try:
            result = self._tts.synthesize(reply_text)
        except TTSError:
            logger.warning("TTS 合成失敗，退化為純文字回覆")
            result = TtsResult(text=reply_text, audio=None)
        # 附上本輪辨識到的長者原話（供 VoiceReplyDelivery 在 debug 模式回傳）。
        return replace(result, transcript=user_text)
