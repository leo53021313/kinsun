"""極簡工具註冊表：註冊工具、產生 specs、dispatch（永不拋）。"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass

from kinsun.llm import ToolSpec

logger = logging.getLogger("kinsun.tools")


@dataclass(frozen=True)
class ToolInvocationContext:
    trace_id: str = ""
    elder_id: str = ""
    has_risk_signal: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, Callable[[dict, ToolInvocationContext | None], str]] = {}

    def register(self, spec: ToolSpec, handler: Callable[[dict], str]) -> None:
        self._specs[spec.name] = spec
        if "context" in inspect.signature(handler).parameters:
            self._handlers[spec.name] = handler
        else:
            self._handlers[spec.name] = lambda arguments, context=None: handler(arguments)

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def dispatch(
        self,
        name: str,
        arguments: dict,
        *,
        context: ToolInvocationContext | None = None,
    ) -> str:
        handler = self._handlers.get(name)
        if handler is None:
            return f"（找不到工具：{name}）"
        try:
            return handler(arguments, context)
        except Exception:  # noqa: BLE001 - 工具失敗不可中斷對話
            logger.exception("工具執行失敗：%s", name)
            return "（工具執行失敗，請稍後再試）"
