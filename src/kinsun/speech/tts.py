"""TTS 介面與 placeholder。真台語 TTS 練好後替換實作，呼叫端不變。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TtsResult:
    text: str
    audio: bytes | None = None


class TTSClient(Protocol):
    def synthesize(self, text: str) -> TtsResult: ...


class TextBubbleTts:
    """placeholder：回文字泡泡，不產音檔（audio=None）。"""

    def synthesize(self, text: str) -> TtsResult:
        return TtsResult(text=text, audio=None)
