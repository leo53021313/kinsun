"""LIFF 身分驗證：驗 ID token 取 LINE userId 與顯示名稱。"""

from __future__ import annotations

import urllib.parse
from typing import NamedTuple, Protocol

from kinsun.transport import Transport, TransportError, UrllibTransport, read_json

_VERIFY_URL = "https://api.line.me/oauth2/v2.1/verify"


class AuthError(Exception):
    """LIFF 身分驗證失敗。"""


class LineIdentity(NamedTuple):
    """LIFF 驗證結果：display_name 供首次建家屬檔命名（✅ 庚-29／F-9），
    來源為 LINE 簽發的 ID token（比前端自送可信）；無 profile scope 時為空字串。"""

    line_user_id: str
    display_name: str


class LiffVerifier(Protocol):
    def verify(self, id_token: str) -> LineIdentity: ...


class LineIdTokenVerifier:
    """POST id_token 到 LINE verify 端點，回傳 LINE userId（sub）＋顯示名稱（name）。"""

    def __init__(
        self, channel_id: str, timeout: float, *, transport: Transport | None = None
    ) -> None:
        self._channel_id = channel_id
        self._timeout = timeout
        self._transport = transport or UrllibTransport()

    def verify(self, id_token: str) -> LineIdentity:
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
        name = payload.get("name")
        return LineIdentity(sub, name if isinstance(name, str) else "")
