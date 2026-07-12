"""綁定閘門：解析「已同意的長輩」才走完整對話。

會話主鍵通道中立後，閘門從「允許與否」加深為「解析出 elder_id」——管線需要
主鍵才能落記憶，故查詢故障時無從放行（fail-open 不再可行），一律回 None
（呼叫端回覆綁定引導語）。解析以 (channel, external_id) 查通道綁定，通道感知。
"""

from __future__ import annotations

import logging
from typing import Protocol

from kinsun.accounts.models import Channel

logger = logging.getLogger("kinsun.binding")


class ElderResolver(Protocol):
    def consented_elder_id(self, channel: Channel, external_id: str) -> str | None: ...


class ConsentGate:
    def __init__(self, resolver: ElderResolver) -> None:
        self._resolver = resolver

    def resolve_elder(self, channel: Channel, external_id: str) -> str | None:
        try:
            return self._resolver.consented_elder_id(channel, external_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "同意解析失敗，視同未綁定 channel=%s external=%s", channel, external_id
            )
            return None


class BindingResolver(Protocol):
    """查綁定不查同意（AllowAllGate 專用）：旁路模式仍以 elder_id 為會話鍵。"""

    def bound_elder_id(self, channel: Channel, external_id: str) -> str | None: ...


class AllowAllGate:
    """全放行閘門：`BINDING_GATE_ENABLED=false` 時使用（demo／開發），不查同意狀態。

    ✅ D-19（丙-2）：有綁定者仍解析為 elder_id——與 ConsentGate 同一會話鍵語意，
    切旗標不再換記憶主鍵；查無綁定（或解析故障）才退回 external_id 充當會話鍵。
    僅限開發環境。"""

    def __init__(self, resolver: BindingResolver | None = None) -> None:
        self._resolver = resolver
        logger.warning("綁定閘門已停用（BINDING_GATE_ENABLED=false），所有使用者可直接對話")

    def resolve_elder(self, channel: Channel, external_id: str) -> str | None:
        if self._resolver is not None:
            try:
                elder_id = self._resolver.bound_elder_id(channel, external_id)
                if elder_id:
                    return elder_id
            except Exception:  # noqa: BLE001 - 旁路模式解析故障退回通道識別，不中斷
                logger.exception("旁路模式綁定解析失敗，退回通道識別 external=%s", external_id)
        return external_id
