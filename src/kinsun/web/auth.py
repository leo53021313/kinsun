"""LIFF 身分驗證：驗 ID token 取 LINE userId。"""

from __future__ import annotations

import urllib.parse
from typing import Protocol

from kinsun.transport import Transport, TransportError, UrllibTransport, read_json

_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"


class AuthError(Exception):
    """LIFF 身分驗證失敗。"""


class LiffVerifier(Protocol):
    def verify(self, id_token: str) -> str: ...


class LineIdTokenVerifier:
    """POST id_token 到 LINE verify 端點，回傳 LINE userId（sub）。"""

    def __init__(
        self, channel_id: str, timeout: float, *, transport: Transport | None = None
    ) -> None:
        self._channel_id = channel_id
        self._timeout = timeout
        self._transport = transport or UrllibTransport()

    def verify(self, id_token: str) -> str:
        data = urllib.parse.urlencode(
            {"id_token": id_token, "client_id": self._channel_id}
        ).encode()
        try:
            response = self._transport.request(
                "POST",
                _VERIFY_URL,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self._timeout,
            )
            payload = read_json(response)
        except TransportError as exc:
            raise AuthError(f"LIFF 驗證呼叫失敗：{exc}") from exc
        sub = payload.get("sub")
        if not isinstance(sub, str):
            raise AuthError("LIFF 驗證回應缺少 sub")
        return sub
