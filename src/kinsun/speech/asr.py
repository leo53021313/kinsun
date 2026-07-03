"""ASR 介面與實作。dev 用 Mock；正式呼叫 DGX 上的 services/asr。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol

from kinsun.config import Settings


class ASRError(Exception):
    """語音辨識失敗。"""


class ASRClient(Protocol):
    def transcribe(self, audio: bytes, *, content_type: str) -> str: ...


class MockAsrClient:
    """dev 用：回固定文字，不連網、不需 GPU。"""

    def __init__(self, transcript: str = "今天天氣真好") -> None:
        self._transcript = transcript

    def transcribe(self, audio: bytes, *, content_type: str) -> str:
        return self._transcript


class DgxAsrClient:
    """正式：POST 原始音檔 bytes 到 DGX 上的 ASR 服務，取回辨識文字。"""

    def __init__(self, endpoint: str, timeout: float) -> None:
        self._endpoint = endpoint
        self._timeout = timeout

    def transcribe(self, audio: bytes, *, content_type: str) -> str:
        request = urllib.request.Request(
            self._endpoint,
            data=audio,
            headers={"Content-Type": content_type},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise ASRError(f"DGX ASR 呼叫失敗：{exc}") from exc
        text = payload.get("text")
        if not isinstance(text, str):
            raise ASRError("DGX ASR 回應缺少 text 欄位")
        return text


def build_asr_client(settings: Settings) -> ASRClient:
    if settings.asr_backend == "dgx":
        if not settings.asr_endpoint:
            raise ASRError("ASR_BACKEND=dgx 但未設定 ASR_ENDPOINT")
        return DgxAsrClient(settings.asr_endpoint, settings.asr_timeout_seconds)
    return MockAsrClient()
