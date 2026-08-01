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


def appointment_day_before_skipped_text(hour: int) -> str:
    """回診「前一天」那顆因為時刻已過而沒建時，要讓**家屬**看見的話。

    少建一顆鬧鐘不可以靜默：家屬設回診時心裡預期的是「前一天也會提醒」，而回診清單
    只顯示一件事、不逐顆列鬧鐘，他沒有別的地方會發現。這句話同時交代替代作法——
    前一天那次改由他自己講，這是他唯一還能做的補救。

    鐘點用 `HH:00` 而不是「早上」：`APPOINTMENT_REMINDER_HOUR` 可調，時段詞一旦被
    改成 21 就會冒出「睡前 21 點」這種話。
    """
    stamp = f"{hour:02d}:00"
    return (
        f"回診前一天的提醒時間（{stamp}）已經過了，這次只設定了回診當天 {stamp} 的提醒；"
        "前一天那次請您自己跟長輩提一聲。"
    )


def appointment_day_before_gone_text(hour: int) -> str:
    """**編輯**既有回診時，「前一天」那顆已過期而沒重建，要讓家屬看見的話。

    ⚠️ **不可沿用 `appointment_day_before_skipped_text`**：那句請家屬「自己跟長輩提
    一聲」，而編輯的情境下前一天那顆很可能**已經正常送出過**——回診 8/5、7/25 建立時
    兩顆都建好了、8/4 早上真的響過，8/4 下午家屬只是改個標題。叫他去做系統已經做過的
    事，就是在跟他說不準確的話。

    要分辨「送過」與「從沒建過」得回頭讀已結案的鬧鐘（`list_for_elder` 依設計濾掉
    `settled_at` 非空的列，讀得到的那份看不見它），成本與這件事的傷害不成比例。兩種
    情形共同為真的只有「更新後只剩當天那顆」這個事實，故這句**只陳述事實**，不對長輩
    是否已被提醒下任何斷言——家屬要接手與否，由他自己判斷。
    """
    stamp = f"{hour:02d}:00"
    return f"回診前一天的提醒時間（{stamp}）已經過了，這次更新後只留下回診當天 {stamp} 的提醒。"


def custom_text(elder_name: str, title: str, minutes_ahead: int) -> str:
    """提前提醒才講「再過幾分鐘」；準時提醒講「提醒您」。"""
    if minutes_ahead > 0:
        return f"{elder_name}，再過 {minutes_ahead} 分鐘要{title}囉。"
    return f"{elder_name}，提醒您：{title}。"
