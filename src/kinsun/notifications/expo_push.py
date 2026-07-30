"""Expo Push Service 客戶端（真推播 D-08 階段 5，2026-07-29）。

為什麼走 Expo 而不是直接接 FCM／APNs：App 是 Expo 專案，Expo Push 用一個 HTTPS
POST 就同時涵蓋兩個平台，憑證由 EAS 代管——排程器是獨立進程，能直接呼叫 HTTP
就不必為了「排程器怎麼把訊息送到那條 WS 連線」蓋一套跨進程匯流排。

⚠️ 這一層只送、不保證送達。Expo 回的是 **ticket**（他們收到了），真正的送達結果
在 **receipt**（要另外拉）。本客戶端只處理 ticket 階段就看得出來的致命錯誤——
`DeviceNotRegistered` 代表那個 token 永久失效，要立刻清掉，否則每次派送都白打。
receipt 輪詢屬於下一階段，尚未實作（見 §未涵蓋）。

未涵蓋（刻意）：
- receipt 輪詢：需要一支排程 job 拉回 ticket 結果，目前送出即結束。
- 600 則／秒的專案速率上限：我們的量級（每位長輩每天數則）離它很遠，先不做節流。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger("kinsun.push")

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
# Expo 單次請求的訊息數上限（官方建議一次最多 100 則）。
_BATCH = 100
# ticket 階段就代表「這個 token 永遠不用再送了」的錯誤碼。
_DEAD_TOKEN_ERRORS = frozenset({"DeviceNotRegistered"})


class PushError(Exception):
    """推播送出失敗（整個請求層級）。"""


@dataclass(frozen=True)
class PushOutcome:
    """一次派送的結果。`dead_tokens` 由呼叫端負責從 store 清掉。"""

    sent: int
    failed: int
    dead_tokens: tuple[str, ...]


class ExpoPushClient:
    def __init__(
        self, *, access_token: str = "", timeout_seconds: float = 10.0, client: object = None
    ) -> None:
        self._access_token = access_token
        self._timeout = timeout_seconds
        # 注入點供測試替換；正式路徑每次建新的 httpx.Client（排程器是短命呼叫）。
        self._client = client

    def send(self, tokens: list[str], title: str, body: str) -> PushOutcome:
        """對多台裝置送同一則訊息。單一 token 壞掉不影響其他台。"""
        if not tokens:
            return PushOutcome(0, 0, ())
        sent = failed = 0
        dead: list[str] = []
        for start in range(0, len(tokens), _BATCH):
            batch = tokens[start : start + _BATCH]
            messages = [{"to": t, "title": title, "body": body, "sound": "default"} for t in batch]
            tickets = self._post(messages)
            for token, ticket in zip(batch, tickets, strict=False):
                if ticket.get("status") == "ok":
                    sent += 1
                    continue
                failed += 1
                error = (ticket.get("details") or {}).get("error", "")
                if error in _DEAD_TOKEN_ERRORS:
                    dead.append(token)
                else:
                    # 其餘錯誤（如 MessageRateExceeded）是暫時性的，留著下次再送。
                    logger.warning("推播 ticket 失敗：%s", ticket.get("message") or error)
        return PushOutcome(sent, failed, tuple(dead))

    def _post(self, messages: list[dict]) -> list[dict]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        try:
            if self._client is not None:
                response = self._client.post(  # type: ignore[attr-defined]
                    EXPO_PUSH_URL, content=json.dumps(messages), headers=headers
                )
            else:
                with httpx.Client(timeout=self._timeout) as client:
                    response = client.post(
                        EXPO_PUSH_URL, content=json.dumps(messages), headers=headers
                    )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - 推播失敗不可中斷提醒派送
            raise PushError(f"Expo 推播送出失敗：{exc}") from exc
        data = payload.get("data")
        if not isinstance(data, list):
            raise PushError(f"Expo 推播回應格式非預期：{payload}")
        return data
