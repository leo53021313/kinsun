"""地點事實提供者：把長輩目前地點注入情境的一段（FactSection）。

⚠️ 本檔的措辭是功能本體，不是文案。

自動注入的結構性弱點是 anchoring：位置每輪無條件進 prompt，模型看到「他在
台南」，問到天氣時就容易順手查台南——而長輩問的地點不必然是他站著的地點
（「等下要去哪吃飯」）。工具方案沒有這個問題（模型得主動要），我們用注入
就得靠措辭扛。故 title 必須把「參考、不是答案」寫死在字面上。

見 spec `2026-07-17-長輩目前地點-design.md` 的「⚠️ anchoring」節。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.locations.store import LocationStore
from kinsun.memory.models import FactSection

_TITLE = "\n這位長者的手機回報的目前位置（僅供參考——他問到的地點不一定是這裡）：\n"

_SECONDS_PER_MINUTE = 60
_SECONDS_PER_HOUR = 3600


def _relative(elapsed_seconds: float) -> str:
    """把「多久以前」講成模型讀得懂的白話。

    模型對 epoch 秒無感，對「3 分鐘前」有感：過期硬門檻擋掉最糟的情況，
    相對時間讓模型在門檻內的邊界情況上仍有判斷依據。

    未滿一分鐘與**未來**（手機時鐘快於伺服器）都講「剛剛」：負數的「-5 分鐘前」
    是胡說八道，退成「剛剛」是誠實的近似。
    """
    if elapsed_seconds < _SECONDS_PER_MINUTE:
        return "剛剛"
    if elapsed_seconds < _SECONDS_PER_HOUR:
        return f"{int(elapsed_seconds // _SECONDS_PER_MINUTE)} 分鐘前"
    return f"{int(elapsed_seconds // _SECONDS_PER_HOUR)} 小時前"


class LocationFacts:
    """facts(elder_id) -> FactSection | None（無資料或已過期回 None）。"""

    def __init__(
        self,
        store: LocationStore,
        *,
        clock: Callable[[], datetime],
        stale_after_hours: int,
    ) -> None:
        self._store = store
        self._clock = clock
        self._stale_after_seconds = stale_after_hours * _SECONDS_PER_HOUR

    def facts(self, elder_id: str) -> FactSection | None:
        location = self._store.get_for_elder(elder_id)
        if location is None:
            return None
        elapsed = self._clock().timestamp() - location.recorded_at
        # 超過門檻才丟，剛好等於門檻仍採信。過期的位置比沒有位置更糟——
        # 與其讓金孫很有自信地報錯天氣，不如讓它照舊開口問。
        if elapsed > self._stale_after_seconds:
            return None
        return FactSection(_TITLE, [f"{_relative(elapsed)}在{location.place}"])
