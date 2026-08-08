"""極簡工具註冊表：註冊工具、產生 specs、dispatch（永不拋）。"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass

from kinsun import tracing
from kinsun.llm import ToolSpec

logger = logging.getLogger("kinsun.tools")

# 工具回傳長度上限（字）。工具回傳的字串會整段進模型的 context——一則長文或一份文件
# 就能把當輪的 context 灌爆、拖慢整輪，而模型真正要的通常只是前面那幾句。
# 截斷處明講被截斷，模型才不會把半句話當成完整答案。
TOOL_OUTPUT_MAX_CHARS = 2000
_TRUNCATED_SUFFIX = "…（內容過長已截斷）"


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

    @tracing.track(type="tool", capture_input=True, capture_output=True)
    def dispatch(
        self,
        name: str,
        arguments: dict,
        *,
        context: ToolInvocationContext | None = None,
    ) -> str:
        # ⚠️ 必須是本函式的第一件事（2026-08-08）：`@track` 的名字在裝飾時就綁死，
        # 而本函式是所有工具共用的單一入口，於是 Opik 上每一個工具都叫 `dispatch`。
        # 排在最前面才涵蓋得到「找不到工具」與「handler 炸掉」——那兩格正是最需要
        # 看出是誰的時候。
        tracing.rename_current_span(f"tool:{name}")
        handler = self._handlers.get(name)
        if handler is None:
            return f"（找不到工具：{name}）"
        # 參數型別守門（2026-07-27）：模型偶爾會把整包參數送成字串或清單。讓 handler
        # 自己去炸，得到的是 `'str' object has no attribute 'get'` 這種對模型毫無幫助的
        # 英文例外——先擋在門口，回一句它看得懂的話。
        if not isinstance(arguments, dict):
            logger.warning("工具參數不是物件：%s（%s）", name, type(arguments).__name__)
            return "（工具參數格式不對，要用物件。請重新組一次參數。）"
        try:
            output = handler(arguments, context)
        except Exception as exc:  # noqa: BLE001 - 工具失敗不可中斷對話
            logger.exception("工具執行失敗：%s", name)
            # ⚠️ 只回**例外類型名**，不回訊息（2026-07-27）：訊息可能是 Python 的英文原文
            # （實測 `'<=' not supported between instances of 'int' and 'str'`），它會整段
            # 進模型 context，最壞的情況是金孫照著唸給長輩聽。類型名對排查夠用，
            # 完整訊息去 logger.exception 與 Opik 查。
            #
            # 也不再說「請稍後再試」——工具迴圈沒有重複偵測，那句話等於在教模型原封
            # 重打同樣的參數，白燒一輪迭代。
            return f"（工具執行失敗：{type(exc).__name__}。不要用同樣參數再試一次。）"
        if len(output) > TOOL_OUTPUT_MAX_CHARS:
            logger.warning("工具回傳過長已截斷：%s（%d 字）", name, len(output))
            return output[:TOOL_OUTPUT_MAX_CHARS] + _TRUNCATED_SUFFIX
        return output
