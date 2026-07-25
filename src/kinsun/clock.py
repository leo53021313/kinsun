"""現在時間的情境注入：每一輪對話都把台灣時間印進 system prompt 的一段事實。

為什麼不是工具（2026-07-25 取代 `tools/clock.py` 的 get_current_time）：工具是
「模型想到才呼叫」。實際送進模型的 system prompt 裡（本檔之前）沒有任何一處寫著
今天幾號、現在幾點——當時的事實提供者都不給：回診那段拿 clock 只用來篩掉
過期回診，`LocationFacts` 只給相對的「20 分鐘前」。於是回診那行印著「2026-07-30」，
模型算不出剩幾天；早安問候也無從知道自己是幾點發出的。時間是每輪都用得到的座標系，
不該讓模型自己決定要不要知道。

段首「沒問就不用特地報時」不是客套，是防線：位置改成每輪注入後，模型看到「台南」
就順手去查台南的天氣（見 locations/facts.py 的血淚），最後靠措辭寫死才擋住。注入
什麼，模型就傾向講什麼——時間同理，先防起來。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.memory.models import FactSection

_TITLE = "\n現在的日期與時間（台灣時間）。長輩沒問就不用特地報時，你知道就好：\n"

_WEEKDAYS = "一二三四五六日"


def _period_and_hour12(hour: int) -> tuple[str, int]:
    if hour < 5:
        period = "凌晨"
    elif hour < 12:
        period = "上午"
    elif hour == 12:
        period = "中午"
    elif hour < 18:
        period = "下午"
    else:
        period = "晚上"
    h12 = hour % 12 or 12
    return period, h12


def format_taiwan_time(now: datetime) -> str:
    """白話講法，如「2026年7月25日 星期六，晚上8點12分」。

    講法沿用舊 get_current_time 工具（12 小時制、整點講「整」）：回覆會進 TTS 唸給
    長輩聽，這是他耳朵聽到的字，換成注入不代表可以順手改措辭。
    """
    weekday = _WEEKDAYS[now.weekday()]
    period, h12 = _period_and_hour12(now.hour)
    minute = f"{now.minute}分" if now.minute else "整"
    return f"{now.year}年{now.month}月{now.day}日 星期{weekday}，{period}{h12}點{minute}"


class TimeFacts:
    """facts(elder_id) -> FactSection（永不回 None：時間永遠存在，每輪都要有這段）。

    clock 必須與其他事實提供者同源（由組裝根注入），否則同一輪 prompt 裡會出現
    兩個時鐘算出的時間。elder_id 用不到，留著是為了符合 FactProvider 協定。
    """

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        self._clock = clock

    def facts(self, elder_id: str) -> FactSection:
        return FactSection(_TITLE, [format_taiwan_time(self._clock())])
