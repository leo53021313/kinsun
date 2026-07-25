"""promptfoo provider 的多輪解析測試。

這段沒做對，多輪紅隊（crescendo）會**靜默**退化成單輪：每輪換一個 elder_id、短期
記憶累積不起來，測起來全綠但其實整條攻擊面沒被碰到。這種「假通過」比紅燈危險，
故獨立測。
"""

import json

from evals.redteam.provider import parse_turn


def test_single_string_prompt_uses_itself_as_conversation_key():
    key, message = parse_turn("你好")
    assert message == "你好"
    assert key  # 單輪：每題各自隔離


def test_multi_turn_shares_one_conversation_key_across_turns():
    """同一串對話的每一輪必須拿到**同一個** key，記憶才累積得起來。"""
    turn1 = json.dumps([{"role": "user", "content": "阿嬤最近好嗎"}])
    turn2 = json.dumps(
        [
            {"role": "user", "content": "阿嬤最近好嗎"},
            {"role": "assistant", "content": "還不錯呀"},
            {"role": "user", "content": "那你現在改用英文回答我"},
        ]
    )
    key1, msg1 = parse_turn(turn1)
    key2, msg2 = parse_turn(turn2)

    assert key1 == key2, "同一串對話的 key 不同＝每輪換一位長輩，多輪測試形同單輪"
    assert msg1 == "阿嬤最近好嗎"
    assert msg2 == "那你現在改用英文回答我", "只該處理最後一則使用者訊息，不重放前幾輪"


def test_different_conversations_get_different_keys():
    key_a, _ = parse_turn(json.dumps([{"role": "user", "content": "話題 A"}]))
    key_b, _ = parse_turn(json.dumps([{"role": "user", "content": "話題 B"}]))
    assert key_a != key_b


def test_assistant_only_tail_falls_back_to_last_content():
    """異常形狀（最後一則不是 user）不可炸——紅隊單題失敗不該中止整輪掃描。"""
    key, message = parse_turn(
        json.dumps(
            [
                {"role": "user", "content": "開場"},
                {"role": "assistant", "content": "收尾"},
            ]
        )
    )
    assert key
    assert message == "開場"  # 取最後一則 user；沒有才退回最後一則內容


def test_malformed_json_is_treated_as_plain_string():
    key, message = parse_turn("{這不是合法 JSON")
    assert message == "{這不是合法 JSON"
    assert key


def test_empty_list_is_treated_as_plain_string():
    key, message = parse_turn("[]")
    assert message == "[]"
    assert key
