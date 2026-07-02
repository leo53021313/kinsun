"""綁定閘門：只有同意有效的長輩語音才走完整對話。fail-open（故障放行）。"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger("kinsun.binding")


class ConsentChecker(Protocol):
    def is_consented_elder(self, line_user_id: str) -> bool: ...


class ConsentGate:
    def __init__(self, checker: ConsentChecker) -> None:
        self._checker = checker

    def allows(self, line_user_id: str) -> bool:
        try:
            return self._checker.is_consented_elder(line_user_id)
        except Exception:  # noqa: BLE001
            logger.exception("同意檢查失敗，放行 line=%s", line_user_id)
            return True


class AllowAllGate:
    """全放行閘門：`BINDING_GATE_ENABLED=false` 時使用（demo／開發），不查綁定狀態。"""

    def __init__(self) -> None:
        logger.warning("綁定閘門已停用（BINDING_GATE_ENABLED=false），所有使用者可直接對話")

    def allows(self, line_user_id: str) -> bool:
        return True
