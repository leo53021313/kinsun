"""錯誤碼中央註冊完整性（✅ 庚-25／A-56）：碼與繁中文案雙向對齊。

拼字錯的碼不在 enum 裡 → 呼叫端 import 就炸（IDE 也會抓）；
新碼漏配文案／文案表殘留孤兒 → 本測試紅。
"""

from __future__ import annotations

from kinsun.web.envelope import ERROR_MESSAGES
from kinsun.web.errors import ErrorCode

# 孤兒文案清單（overloaded 已於庚-43 移除，現為空）。
_PENDING_REMOVAL: set[str] = set()


def test_every_error_code_has_traditional_chinese_message():
    missing = [code.value for code in ErrorCode if code.value not in ERROR_MESSAGES]
    assert missing == [], f"錯誤碼缺繁中文案：{missing}"


def test_no_orphan_messages_outside_registry():
    known = {code.value for code in ErrorCode} | _PENDING_REMOVAL
    orphans = [key for key in ERROR_MESSAGES if key not in known]
    assert orphans == [], f"文案表有未註冊的孤兒碼：{orphans}"
