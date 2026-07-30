"""TTS 介面與實作。dev 用文字泡泡 placeholder；正式呼叫 DGX 上的 services/tts。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from kinsun.transport import HttpxTransport, Transport, TransportError, header_value


class TTSError(Exception):
    """語音合成失敗。"""


@dataclass(frozen=True)
class TtsResult:
    text: str
    audio: bytes | None = None
    duration_ms: int = 0
    transcript: str = ""  # 本輪 ASR 辨識到的長者原話（debug 用，不進語音合成）


@dataclass(frozen=True)
class VoiceReference:
    """長輩的客製化參考語音（聲音克隆用）；未提供則沿用 DGX 端全域預設聲音。"""

    elder_id: str
    prompt_audio_url: str
    prompt_text: str


class TTSClient(Protocol):
    def synthesize(self, text: str, *, voice: VoiceReference | None = None) -> TtsResult: ...


class TextBubbleTts:
    """placeholder：回文字泡泡，不產音檔（audio=None）。"""

    def synthesize(self, text: str, *, voice: VoiceReference | None = None) -> TtsResult:
        return TtsResult(text=text, audio=None)


class DgxTtsClient:
    """正式：POST {"text"} 到 DGX 上的 TTS 服務，取回 m4a bytes 與時長。"""

    def __init__(
        self,
        endpoint: str,
        timeout: float,
        *,
        api_key: str = "",
        transport: Transport | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._timeout = timeout
        self._api_key = api_key
        self._transport = transport or HttpxTransport()

    def synthesize(self, text: str, *, voice: VoiceReference | None = None) -> TtsResult:
        payload: dict[str, str] = {"text": text}
        if voice is not None:
            payload["elder_id"] = voice.elder_id
            payload["prompt_audio_url"] = voice.prompt_audio_url
            payload["prompt_text"] = voice.prompt_text
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._api_key:  # 共用金鑰（✅ D-56 丙-10）；未設＝內網開發模式
            headers["X-Api-Key"] = self._api_key
        try:
            response = self._transport.request(
                "POST",
                self._endpoint,
                data=body,
                headers=headers,
                timeout=self._timeout,
            )
        except TransportError as exc:
            raise TTSError(f"DGX TTS 呼叫失敗：{exc}") from exc
        audio = response.body
        raw_ms = header_value(response, "X-Duration-Ms")
        if raw_ms is None:
            raise TTSError("DGX TTS 回應缺少 X-Duration-Ms 標頭")
        try:
            duration_ms = int(raw_ms)
        except ValueError as exc:
            raise TTSError(f"DGX TTS 回應 X-Duration-Ms 非整數：{raw_ms!r}") from exc
        return TtsResult(text=text, audio=audio, duration_ms=duration_ms)


def build_tts_client(settings) -> TTSClient:
    if settings.tts_backend == "dgx":
        if not settings.tts_endpoint:
            raise TTSError("TTS_BACKEND=dgx 但未設定 TTS_ENDPOINT")
        return DgxTtsClient(
            settings.tts_endpoint, settings.tts_timeout_seconds, api_key=settings.tts_api_key
        )
    return TextBubbleTts()
