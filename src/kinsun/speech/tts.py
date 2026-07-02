"""TTS 介面與實作。dev 用文字泡泡 placeholder；正式呼叫 DGX 上的 services/tts。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class TTSError(Exception):
    """語音合成失敗。"""


@dataclass(frozen=True)
class TtsResult:
    text: str
    audio: bytes | None = None
    duration_ms: int = 0


class TTSClient(Protocol):
    def synthesize(self, text: str) -> TtsResult: ...


class TextBubbleTts:
    """placeholder：回文字泡泡，不產音檔（audio=None）。"""

    def synthesize(self, text: str) -> TtsResult:
        return TtsResult(text=text, audio=None)


class DgxTtsClient:
    """正式：POST {"text"} 到 DGX 上的 TTS 服務，取回 m4a bytes 與時長。"""

    def __init__(self, endpoint: str, timeout: float) -> None:
        self._endpoint = endpoint
        self._timeout = timeout

    def synthesize(self, text: str) -> TtsResult:
        body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                audio = response.read()
                raw_ms = response.headers.get("X-Duration-Ms")
        except (urllib.error.URLError, OSError) as exc:
            raise TTSError(f"DGX TTS 呼叫失敗：{exc}") from exc
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
        return DgxTtsClient(settings.tts_endpoint, settings.tts_timeout_seconds)
    return TextBubbleTts()
