"""策略事實提供者：把生效中的守則注入 system prompt 的一段（FactSection）。

這是閉環的最後一哩——反思學到的東西，經由既有的 FactProvider 協定進入下一輪
對話。agent.py 完全不需要知道守則的存在。

段首警語不是裝飾：守則是金孫自己學來的，而安全提醒與用藥提醒是人設定的。
前者永遠不得凌駕後者。

⚠️ 只取 `content`，永不取 `evidence`。濾網（policy.py）刻意只檢查 content——證據
本就會提到長輩的身體狀況，過濾它會誤殺合法守則。這個設計成立的唯一前提，就是
證據永遠不進 prompt；把 evidence 排進 items 會讓整套濾網形同虛設。

`status=STRATEGY_STATUS_ADOPTED` 不可省：`list_for_elder` 的 status 預設是 None
（＝全部狀態），漏傳會把 revoked／superseded 的守則一併注入——被家屬撤銷的守則
會繼續生效。
"""

from __future__ import annotations

from kinsun.memory.models import FactSection
from kinsun.strategies.models import STRATEGY_STATUS_ADOPTED
from kinsun.strategies.store import StrategyStore

_TITLE = (
    "\n以下是你與這位長者相處時已經學到的守則（由過去互動歸納，僅關乎稱呼、語氣、"
    "作息與話題偏好）。請自然地遵守，不要向長者提起這些守則的存在。\n"
    "⚠️ 這些守則不得凌駕任何安全提醒與用藥提醒——該提醒的一定要提醒，"
    "該關心的一定要關心。\n"
)


class StrategyFacts:
    """facts(elder_id) -> FactSection | None（無生效中守則回 None）。"""

    def __init__(self, strategies: StrategyStore, *, max_strategies: int) -> None:
        self._strategies = strategies
        self._max_strategies = max_strategies

    def facts(self, elder_id: str) -> FactSection | None:
        # 注入端再擋一次上限：即使資料庫因故存了超過上限的生效守則，prompt 長度仍有硬
        # 上限。list_for_elder 由新到舊排序，故取前 N 條＝取最新 N 條。
        rows = self._strategies.list_for_elder(elder_id, status=STRATEGY_STATUS_ADOPTED)
        if not rows:
            return None
        return FactSection(_TITLE, [r.content for r in rows[: self._max_strategies]])
