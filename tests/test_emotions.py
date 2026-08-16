"""阿白的表情詞彙必須與角色 renderer 完全一致。

⚠️ 這兩份清單分屬 Python 與 JavaScript 兩個世界，型別檢查連不起來。漂掉的症狀不是
錯誤訊息，而是「阿白某天開始不動表情」（挑到 renderer 不認得的字就整個忽略）或
「阿白對著長輩生氣」（黑名單少一項）——都要等長輩真的遇上那一刻才看得到。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kinsun.emotions import (
    AVATAR_EMOTIONS,
    BLOCKED_EMOTIONS,
    FALLBACK_EMOTION,
    SELECTABLE_EMOTIONS,
    sanitize_emotion,
)

CORE = Path(__file__).resolve().parents[1] / "shared" / "otto-pet-core"


def _renderer_emotions() -> list[str]:
    body = (CORE / "emotions.js").read_text(encoding="utf-8").split("PET.EMOTIONS = {", 1)[1]
    return re.findall(r"^    ([a-zA-Z]+): E\(\{", body, re.MULTILINE)


def _renderer_blocked() -> list[str]:
    source = (CORE / "sentiment.js").read_text(encoding="utf-8")
    block = re.search(r"BLOCKED_EMOTIONS = new Set\(\[([\s\S]*?)\]\)", source)
    assert block is not None, "sentiment.js 找不到 BLOCKED_EMOTIONS"
    return re.findall(r'"([a-z]+)"', block.group(1))


def test_avatar_emotions_match_renderer():
    renderer = _renderer_emotions()
    assert renderer, "解析 emotions.js 失敗——格式改了就要一起改這支測試"
    assert sorted(AVATAR_EMOTIONS) == sorted(renderer)


def test_blocked_emotions_match_renderer():
    assert sorted(BLOCKED_EMOTIONS) == sorted(_renderer_blocked())


def test_no_duplicate_emotions():
    assert len(AVATAR_EMOTIONS) == len(set(AVATAR_EMOTIONS))


def test_blocked_are_real_emotions():
    """黑名單裡的每一項都必須真的存在於情緒表——角色改版改名時，黑名單會安靜失效。"""
    assert BLOCKED_EMOTIONS <= set(AVATAR_EMOTIONS)


def test_selectable_excludes_blocked():
    assert set(SELECTABLE_EMOTIONS).isdisjoint(BLOCKED_EMOTIONS)
    assert set(SELECTABLE_EMOTIONS) | set(BLOCKED_EMOTIONS) == set(AVATAR_EMOTIONS)


def test_fallback_is_selectable():
    assert FALLBACK_EMOTION in SELECTABLE_EMOTIONS


@pytest.mark.parametrize("blocked", sorted(BLOCKED_EMOTIONS))
def test_sanitize_rejects_blocked(blocked: str):
    assert sanitize_emotion(blocked) == FALLBACK_EMOTION


@pytest.mark.parametrize("value", ["", None, "   ", "not_an_emotion", "HAPPY", "開心"])
def test_sanitize_rejects_unknown(value: str | None):
    """⚠️ 大小寫不放行：renderer 是逐字比對，`HAPPY` 對它就是不存在的表情。"""
    assert sanitize_emotion(value) == FALLBACK_EMOTION


def test_sanitize_tolerates_surrounding_space():
    """前後空白是格式雜訊、不是語意問題——把一個畫得出來的表情降級成平靜沒有好處。"""
    assert sanitize_emotion(" happy ") == "happy"


def test_sanitize_keeps_good_emotions():
    for emotion in ("happy", "touched", "sick", "hurt", "apologetic", "lonely"):
        assert sanitize_emotion(emotion) == emotion
