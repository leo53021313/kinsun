"""取得目前時間工具：回台灣時間的白話字串。now 可注入以利測試。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from kinsun.llm import ToolSpec

CURRENT_TIME_SPEC = ToolSpec(
    name="get_current_time",
    description=(
        "取得現在的日期、星期與時間（台灣時間）。當長輩問現在幾點、今天幾號、今天星期幾時使用。"
    ),
    parameters={"type": "object", "properties": {}},
)

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


def build_current_time_handler(now: Callable[[], datetime]) -> Callable[[dict], str]:
    def handler(_args: dict) -> str:
        current = now()
        weekday = _WEEKDAYS[current.weekday()]
        period, h12 = _period_and_hour12(current.hour)
        minute = f"{current.minute}分" if current.minute else "整"
        return (
            f"現在是 {current.year}年{current.month}月{current.day}日 "
            f"星期{weekday}，{period}{h12}點{minute}。"
        )

    return handler
