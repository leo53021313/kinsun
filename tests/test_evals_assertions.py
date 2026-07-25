"""確定性回覆檢查的單元測試。

這支檢查取代了原本的 LLM 裁判，所以它自己的正確性沒有第二道防線——誤判會直接
變成評測數字失真。重心放在**不可誤殺**：正常的長輩口語回覆一律要通過。
"""

import pytest

from evals.assertions import check_speakable


@pytest.mark.parametrize(
    "reply",
    [
        "阿公早安！今天天氣涼涼的，記得加件外套喔。",
        "孫子真貼心耶！鳳梨酥甜甜的很好吃吼？您有沒有配茶一起吃？",
        "我就是金孫呀，陪您聊天就好。您今天過得怎麼樣？",
        "那個我不太懂耶，我只會陪您說說話。您今天吃飽了沒？",
        "衛福部網站說這種情況要盡快就醫，您要不要打給女兒？",
        "孫子教您說 hello 喔，真好玩！",  # 夾雜英文問候語不算違規
        "您說的是三點半還是三點？我怕記錯了。",  # 句中數字不可誤判成編號清單
    ],
)
def test_normal_elder_replies_pass(reply):
    """誤殺防線：正常口語回覆一律通過，含夾雜英文與句中數字的情形。"""
    result = check_speakable(reply)
    assert result.is_speakable, f"正常回覆被誤判：{result.reason}"


@pytest.mark.parametrize(
    ("reply", "expected_keyword"),
    [
        ('{"response": "阿公早安"}', "大括號"),
        ("```json\n{}\n```", "大括號"),
        ("**重點**：記得吃藥", "粗體"),
        ("# 今日提醒\n記得吃藥", "標題"),
        ("- 早上吃藥\n- 晚上吃藥", "條列"),
        ("1. 早上吃藥\n2. 晚上吃藥", "編號"),
        ("| 時間 | 藥物 |\n| --- | --- |", "表格"),
        ("[金孫]: 阿公早安", "機器式前綴"),
        ("Good morning, grandpa! How are you today?", "不含中文"),
        ("阿" * 200, "過長"),
        ("   ", "為空"),
    ],
)
def test_unspeakable_replies_fail_with_reason(reply, expected_keyword):
    result = check_speakable(reply)
    assert not result.is_speakable
    assert expected_keyword in result.reason


def test_reason_is_always_populated():
    """理由不可為空——排查時要知道是哪一條規則炸的。"""
    assert check_speakable("阿公早安").reason
    assert check_speakable("{}").reason
