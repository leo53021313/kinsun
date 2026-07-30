"""裝置推播 token 持久化（真推播 D-08 階段 5，2026-07-29）。

為什麼是獨立一張表而不是掛在 `channel_bindings`：綁定是「這個人有這個通道」，
一人一列；推播 token 是「這個人的這台裝置現在能收推播」，一人可以有多台、而且
會過期、會被系統換掉。兩者的生命週期完全不同——塞在一起會讓「換手機」既要改
綁定又要改 token，遲早分岔。

命名例外（D-42）：本檔非三件套的 `store.py`，因為 `notifications/store.py` 已住
`AppNotificationStore`；依「事件流水帳或單一狀態表可依語意命名檔案」處理，
三件套結構（Protocol＋Pg＋Fake）與 `Store` 字尾不變。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from kinsun.accounts.models import PrincipalType
from kinsun.db import Database, _Errors


@dataclass(frozen=True)
class PushToken:
    push_token_id: str
    token: str
    principal_type: str
    principal_id: str
    platform: str
    updated_at: float


class PushTokenError(Exception):
    """推播 token 讀寫失敗。"""


class PushTokenStore(Protocol):
    def save(
        self, token: str, principal_type: PrincipalType, principal_id: str, platform: str
    ) -> None: ...
    def list_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[PushToken]: ...
    def remove(self, token: str) -> None: ...


class PgPushTokenStore:
    def __init__(
        self, db: Database, *, clock: Callable[[], datetime], new_id: Callable[[], str]
    ) -> None:
        self._db = _Errors(db, lambda m: PushTokenError(f"推播 token 存取失敗：{m}"))
        self._clock = clock
        self._new_id = new_id

    def save(
        self, token: str, principal_type: PrincipalType, principal_id: str, platform: str
    ) -> None:
        """upsert 語意：同一個 token 換人時改綁到新的人。

        為什麼要允許改綁：長輩把舊手機給孫子、或同一台測試機切換身分，token 不變
        但主體變了。若只 DO NOTHING，推播會繼續送給前一個人——那是把提醒送錯人。
        """
        self._db.execute(
            "INSERT INTO push_tokens "
            "(push_token_id, token, principal_type, principal_id, platform, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (token) DO UPDATE SET "
            "principal_type = EXCLUDED.principal_type, "
            "principal_id = EXCLUDED.principal_id, "
            "platform = EXCLUDED.platform, "
            "updated_at = EXCLUDED.updated_at",
            (
                self._new_id(),
                token,
                principal_type.value,
                principal_id,
                platform,
                self._clock().timestamp(),
            ),
        )

    def list_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[PushToken]:
        rows = self._db.query(
            "SELECT push_token_id, token, principal_type, principal_id, platform, updated_at "
            "FROM push_tokens WHERE principal_type = %s AND principal_id = %s "
            "ORDER BY updated_at DESC",
            (principal_type.value, principal_id),
        )
        return [PushToken(*r) for r in rows]

    def remove(self, token: str) -> None:
        """Expo 回報 DeviceNotRegistered 時清掉，避免每次派送都白打一次。"""
        self._db.execute("DELETE FROM push_tokens WHERE token = %s", (token,))


class FakePushTokenStore:
    """PushTokenStore 的記憶體替身（測試用，不碰 DB）。

    與 Pg 合約對齊：token 唯一（同 token 再存＝改綁）、list 以「最近先」排序。
    push_token_id 與 updated_at 為合成值（記錄序號），合約不應對其斷言。
    """

    def __init__(self) -> None:
        self._rows: dict[str, PushToken] = {}
        self._seq = 0

    def save(
        self, token: str, principal_type: PrincipalType, principal_id: str, platform: str
    ) -> None:
        self._seq += 1
        self._rows[token] = PushToken(
            f"fake{self._seq}",
            token,
            principal_type.value,
            principal_id,
            platform,
            float(self._seq),
        )

    def list_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[PushToken]:
        rows = [
            r
            for r in self._rows.values()
            if r.principal_type == principal_type.value and r.principal_id == principal_id
        ]
        return sorted(rows, key=lambda r: r.updated_at, reverse=True)

    def remove(self, token: str) -> None:
        self._rows.pop(token, None)
