"""排程訊息措辭：時段詞對應與三種 kind 的組字（純函式，無 I/O）。"""

from __future__ import annotations

import pytest

from kinsun.schedules.wording import (
    appointment_texts,
    custom_text,
    medication_text,
    slot_label,
)


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(8, "早上"), (12, "中午"), (18, "晚上"), (21, "睡前")],
)
def test_default_medication_hours_keep_their_original_words(hour, expected):
    # 四個預設鐘點必須落回原本的詞——家屬不改設定，長輩聽到的字就一字不變。
    assert slot_label(hour) == expected


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, "早上"),
        (7, "早上"),
        (11, "中午"),
        (14, "中午"),
        (15, "晚上"),
        (19, "晚上"),
        (20, "睡前"),
        (23, "睡前"),
    ],
)
def test_slot_label_covers_every_hour(hour, expected):
    assert slot_label(hour) == expected


def test_medication_text_matches_the_legacy_wording():
    # 與 medications/jobs.py:44 逐字相同。
    assert medication_text("阿嬤", 8, ["血壓藥", "胃藥"]) == "阿嬤，早上該吃藥囉：血壓藥、胃藥"


def test_appointment_texts_match_the_legacy_wording_with_time():
    elder, guardian = appointment_texts("阿公", "心臟科回診 林口長庚", "明天", "10:30")
    assert elder == (
        "阿公，明天 10:30 要回診囉：心臟科回診 林口長庚。記得準時，需要的話請家人陪您去。"
    )
    assert guardian == "【金孫提醒】阿公 明天 10:30 要回診——心臟科回診 林口長庚。"


def test_appointment_texts_omit_the_time_when_unknown():
    # 舊行為：time 為空＝提醒不帶時間，且「今天」後面不留多餘空格。
    elder, guardian = appointment_texts("阿公", "牙科", "今天", "")
    assert elder == "阿公，今天要回診囉：牙科。記得準時，需要的話請家人陪您去。"
    assert guardian == "【金孫提醒】阿公 今天要回診——牙科。"


def test_custom_text_without_lead_time():
    assert custom_text("阿嬤", "去吃飯", 0) == "阿嬤，提醒您：去吃飯。"


def test_custom_text_with_lead_time():
    assert custom_text("阿嬤", "出門", 15) == "阿嬤，再過 15 分鐘要出門囉。"
