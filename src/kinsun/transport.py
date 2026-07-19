"""app 層對外 HTTP 的統一出口（傳輸層）。

`Transport` 只有一個 `request`；正式用 `UrllibTransport`，錯誤統一為 `TransportError`。
各 client（asr／tts／audio／auth／weather）建構時可注入 transport（預設 `UrllibTransport`），
測試注入 `FakeTransport` 即可，不必 monkeypatch urllib 全域。便利函式 `get_json`／
`read_json` 讓「讀 JSON」有一致寫法，且對真假 Transport 皆通用。無重試。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class TransportError(Exception):
    """對外 HTTP 請求失敗（連線／逾時／HTTP 錯誤狀態／回應無法解析）。"""


@dataclass(frozen=True)
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes


class Transport(Protocol):
    def request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float,
    ) -> Response: ...


class UrllibTransport:
    """以標準庫 urllib 實作的 Transport。無重試；逾時與錯誤統一翻成 TransportError。"""

    def request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float,
    ) -> Response:
        request = urllib.request.Request(url, data=data, headers=dict(headers or {}), method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return Response(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                )
        except (urllib.error.URLError, OSError) as exc:
            raise TransportError(f"HTTP 請求失敗：{url}：{exc}") from exc


def header_value(response: Response, name: str) -> str | None:
    """取回應標頭值，名稱不分大小寫（RFC 9110）；不存在回 None。

    真實線路上 uvicorn/Starlette 一律送小寫標頭名，直接對 headers dict 用
    原寫法 get 會永遠查不到。
    """
    lowered = name.lower()
    for key, value in response.headers.items():
        if key.lower() == lowered:
            return value
    return None


def read_json(response: Response) -> Any:
    """把回應 body 解為 JSON（物件或陣列）；解析失敗一律 TransportError。"""
    try:
        return json.loads(response.body)
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as exc:
        raise TransportError(f"回應非合法 JSON：{exc}") from exc


def get_json(
    transport: Transport,
    url: str,
    *,
    timeout: float,
    headers: Mapping[str, str] | None = None,
) -> Any:
    """GET 並將回應解為 JSON。"""
    return read_json(transport.request("GET", url, headers=headers, timeout=timeout))


class FakeTransport:
    """測試用 Transport：依序回吐預排的 Response，並記錄每次 request 供斷言。

    設定 `error` 可讓下一次 request 改為丟出該例外（模擬連線失敗）。
    """

    def __init__(
        self,
        responses: list[Response] | None = None,
        *,
        handler: Callable[[str, str, bytes | None], Response] | None = None,
    ) -> None:
        self.calls: list[tuple[str, str, bytes | None, dict[str, str], float]] = []
        self.error: Exception | None = None
        self._responses = list(responses or [])
        self._handler = handler

    def request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float,
    ) -> Response:
        self.calls.append((method, url, data, dict(headers or {}), timeout))
        if self.error is not None:
            raise self.error
        if self._handler is not None:
            return self._handler(method, url, data)
        if self._responses:
            return self._responses.pop(0)
        return Response(200, {}, b"")
