"""通道中立的出站路由：把「本人」的訊息 fan-out 到其所有綁定通道。

主動關懷、提醒 jobs、危急通知只認「本人（principal）」；由本路由查
channel_bindings 決定實際走哪些通道。新增通道＝多註冊一個 adapter，呼叫端不變。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol

from kinsun.accounts.models import Channel, ChannelBinding, PrincipalType
from kinsun.channels.outbound import OutboundChannel

logger = logging.getLogger("kinsun.channels.router")


class BindingDirectory(Protocol):
    def list_channel_bindings_for_principal(
        self, principal_type: PrincipalType, principal_id: str
    ) -> list[ChannelBinding]: ...


class ChannelRouter:
    """本人 → 綁定通道的出站路由：對每個已綁定且有 adapter 的通道各送一次。
    單一通道失敗只記錄、不中斷其他通道。"""

    def __init__(
        self, directory: BindingDirectory, channels: Mapping[Channel, OutboundChannel]
    ) -> None:
        self._directory = directory
        self._channels = channels

    def _routes(self, principal_type: PrincipalType, principal_id: str) -> list[ChannelBinding]:
        bindings = self._directory.list_channel_bindings_for_principal(principal_type, principal_id)
        return [b for b in bindings if b.channel in self._channels]

    def has_route(self, principal_type: PrincipalType, principal_id: str) -> bool:
        return bool(self._routes(principal_type, principal_id))

    def send_text(self, principal_type: PrincipalType, principal_id: str, text: str) -> int:
        """對本人的每個可達通道各送一次文字；回傳成功送出的通道數。"""
        return len(self.send_text_channels(principal_type, principal_id, text))

    def send_text_channels(
        self, principal_type: PrincipalType, principal_id: str, text: str
    ) -> list[str]:
        """同 send_text，但回傳實際成功的通道名（✅ 庚-16）——供送達留痕標註語意
        （如 App 僅為落庫待拉取、非真送達）。"""
        succeeded: list[str] = []
        for binding in self._routes(principal_type, principal_id):
            try:
                self._channels[binding.channel].send_text(binding.external_id, text)
                succeeded.append(binding.channel.value)
            except Exception:  # noqa: BLE001 - 單一通道失敗不可中斷其他通道
                logger.exception(
                    "出站通道送出失敗 channel=%s principal=%s", binding.channel, principal_id
                )
        return succeeded
