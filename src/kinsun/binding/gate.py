"""綁定閘門：解析「已同意的長輩」才走完整對話。

會話主鍵通道中立後，閘門從「允許與否」加深為「解析出 elder_id」——管線需要
主鍵才能落記憶，故查詢故障時無從放行（fail-open 不再可行），一律回 None
（呼叫端回覆綁定引導語）。
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("kinsun.binding")


class ElderResolver(Protocol):
    def consented_elder_id(self, line_user_id: str) -> str | None: ...


class ConsentGate:
    def __init__(self, resolver: ElderResolver) -> None:
        self._resolver = resolver

    def resolve_elder(self, line_user_id: str) -> str | None:
        try:
            return self._resolver.consented_elder_id(line_user_id)
        except Exception:  # noqa: BLE001
            logger.exception("同意解析失敗，視同未綁定 line=%s", line_user_id)
            return None


class AllowAllGate:
    """全放行閘門：`BINDING_GATE_ENABLED=false` 時使用（demo／開發），不查綁定狀態。
    直接以 line_user_id 充當會話鍵（記憶會落在通道識別下），僅限開發環境。"""

    def __init__(self) -> None:
        logger.warning("綁定閘門已停用（BINDING_GATE_ENABLED=false），所有使用者可直接對話")

    def resolve_elder(self, line_user_id: str) -> str | None:
        return line_user_id
