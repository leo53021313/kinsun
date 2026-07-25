"""排程提醒的措辭：純函式、無 I/O、不經 LLM。

不經 LLM 與現行用藥／回診 job 一致：措辭可預期、零成本，也不會因模型漂移而變調。

時段詞刻意**不重用** `clock.py` 的 `_period_and_hour12`：那套詞彙是凌晨／上午／
中午／下午／晚上（報時用），而用藥講的是早上／中午／晚上／睡前。混用會讓 08:00
從「早上該吃藥」變成「上午該吃藥」、21:00 從「睡前」變成「晚上」。下面的分界點
挑成讓四個預設鐘點（8／12／18／21）落回原本的詞——家屬不改設定，長輩聽到的字
就一字不變；改成 07:30 才會聽到「早上」，仍然自然。
"""

from __future__ import annotations

_MORNING_UNTIL = 11
_NOON_UNTIL = 15
_EVENING_UNTIL = 20


def slot_label(hour: int) -> str:
    if hour < _MORNING_UNTIL:
        return "早上"
    if hour < _NOON_UNTIL:
        return "中午"
    if hour < _EVENING_UNTIL:
        return "晚上"
    return "睡前"


def medication_text(elder_name: str, hour: int, titles: list[str]) -> str:
    """與 medications/jobs.py 的舊訊息逐字相同。"""
    return f"{elder_name}，{slot_label(hour)}該吃藥囉：{'、'.join(titles)}"


def appointment_texts(
    elder_name: str, title: str, when_word: str, event_time: str
) -> tuple[str, str]:
    """回傳（長輩版, 家屬版），與 appointments/jobs.py 的舊訊息逐字相同。

    event_time 為空＝未指定看診時刻，提醒不帶時間（庚-15 的舊語意），且「今天」
    後面不留多餘空格。
    """
    when_phrase = f"{when_word} {event_time} " if event_time else when_word
    elder = f"{elder_name}，{when_phrase}要回診囉：{title}。記得準時，需要的話請家人陪您去。"
    guardian = f"【金孫提醒】{elder_name} {when_phrase}要回診——{title}。"
    return elder, guardian


def custom_text(elder_name: str, title: str, minutes_ahead: int) -> str:
    """提前提醒才講「再過幾分鐘」；準時提醒講「提醒您」。"""
    if minutes_ahead > 0:
        return f"{elder_name}，再過 {minutes_ahead} 分鐘要{title}囉。"
    return f"{elder_name}，提醒您：{title}。"
