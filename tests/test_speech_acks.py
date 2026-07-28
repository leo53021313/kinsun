"""安撫話語庫的守門測試。

最重要的一條是 `test_default_persona_covers_every_registered_tool`：它以 `pkgutil`
走遍 `kinsun.tools` 蒐集**每一個**模組級 `ToolSpec`，所以新增工具檔會自動被納入
掃描範圍——**不需要有人記得回來更新這份測試**。這正是它與「手寫一份工具清單去比對」
的差別：後者本身也會忘記更新。
"""

from __future__ import annotations

import importlib
import pkgutil
import random

import pytest

import kinsun.tools as tools_pkg
from evals.assertions import check_speakable
from kinsun.llm import ToolSpec
from kinsun.speech import acks


def _registered_tool_names() -> set[str]:
    """走遍 kinsun.tools 下每個模組，蒐集所有模組級 ToolSpec 的名字。

    這是執行期之外唯一的權威清單：`ToolRegistry` 要組裝整個 app 才拿得到，
    而工具是否註冊還取決於金鑰與 store 有沒有設定（`composition.py` 的條件註冊）。
    模組級常數不受那些條件影響，正好是「這個專案有哪些工具」的完整集合。
    """
    names: set[str] = set()
    for module_info in pkgutil.iter_modules(tools_pkg.__path__):
        module = importlib.import_module(f"{tools_pkg.__name__}.{module_info.name}")
        names |= {value.name for value in vars(module).values() if isinstance(value, ToolSpec)}
    return names


def test_registered_tool_scan_actually_finds_tools():
    """先證明掃描本身有偵測力——掃不到東西的話，下面那條涵蓋率測試會空轉通過。"""
    found = _registered_tool_names()
    assert len(found) >= 10, f"只掃到 {len(found)} 個工具，掃描邏輯可能壞了"
    assert "get_news" in found
    assert "search_nearby_places" in found


def test_default_persona_covers_every_registered_tool():
    """⭐ 新增工具時漏配安撫話，這條會紅。

    `USE_GENERIC`（空 tuple）算涵蓋——那是「刻意用通用句」的明確表態；
    真正要擋的是**整個鍵不存在**，也就是新增工具時忘了回來語庫表態。
    """
    missing = _registered_tool_names() - set(acks.persona().by_tool)
    assert not missing, (
        f"這些工具沒有在 speech/acks.py 的 DEFAULT_PERSONA.by_tool 裡表態：{sorted(missing)}。"
        "請補上專屬句子，或明寫 USE_GENERIC 表示刻意使用通用句。"
    )


def test_no_stale_entries_for_tools_that_no_longer_exist():
    """反向把關：工具刪掉後語庫留下的孤兒鍵應一併清掉，否則語庫會越積越髒。"""
    stale = set(acks.persona().by_tool) - _registered_tool_names()
    assert not stale, f"語庫裡有已不存在的工具：{sorted(stale)}"


@pytest.mark.parametrize("name", sorted(acks.personas()))
def test_every_persona_has_a_non_empty_generic_pool(name):
    """通用句是兩軸保底的最後一層，空掉的話某些工具就永遠沒有安撫話。"""
    assert acks.persona(name).generic, f"人設 {name} 的 generic 是空的"


@pytest.mark.parametrize("phrase", acks.all_phrases())
def test_every_phrase_is_speakable(phrase):
    """每一句都會被 TTS 原封唸出來，故沿用 evals 既有的可唸性斷言。"""
    result = check_speakable(phrase)
    assert result.is_speakable, f"「{phrase}」不可唸：{result.reason}"


@pytest.mark.parametrize("phrase", acks.all_phrases())
def test_no_phrase_claims_the_work_is_already_done(phrase):
    """⚠️ 安撫話是在工具**還沒跑**的時候唸出去的。

    說「記好了」「查到了」而工具隨後失敗，等於對長輩說謊——語料實錄過模型犯這個錯
    （「好，我馬上幫您記下來。晚上七點記得吃血壓藥喔！」，`create_schedule` 尚未執行）。
    我們自己寫的句子更不該犯。
    """
    done_claims = ("好了", "記下來了", "查到了", "找到了", "已經", "幫您取消了", "完成")
    hit = [word for word in done_claims if word in phrase]
    assert not hit, f"「{phrase}」宣稱工作已完成（{hit}），但這句話在工具跑之前就會唸出去"


@pytest.mark.parametrize("phrase", acks.all_phrases())
def test_every_phrase_is_short_enough_to_stay_cheap(phrase):
    """TTS 是 0.9 秒固定成本＋每字 0.10 秒；安撫話的全部價值就是「立刻」。

    上限 18 字＝語料裡合格安撫話的實際最大值。超過就是在把省下來的延遲還回去。
    """
    assert len(phrase) <= 18, f"「{phrase}」{len(phrase)} 字，超過 18 字上限"


def test_unknown_persona_falls_back_to_the_default_one():
    assert acks.persona("還沒做的人設") is acks.persona(acks.DEFAULT_PERSONA)
    assert acks.phrases_for("get_news", persona_name="還沒做的人設") == acks.phrases_for("get_news")


def test_tool_marked_use_generic_falls_back_to_the_generic_pool():
    """`web_search` 刻意用通用句（語料 6/6 模型自己也是）。"""
    assert acks.persona().by_tool["web_search"] == acks.USE_GENERIC
    assert acks.phrases_for("web_search") == acks.persona().generic


def test_unknown_tool_falls_back_to_the_generic_pool():
    assert acks.phrases_for("還沒做的工具") == acks.persona().generic


def test_pick_returns_a_phrase_from_the_right_pool():
    rng = random.Random(0)
    for _ in range(20):
        assert acks.pick("get_news", rng=rng) in acks.phrases_for("get_news")
        assert acks.pick("web_search", rng=rng) in acks.persona().generic


def test_all_phrases_is_deduplicated_and_stable():
    phrases = acks.all_phrases()
    assert len(phrases) == len(set(phrases))
    assert acks.all_phrases() == phrases
    # 通用句與逐工具句都要進預熱清單，漏掉哪一邊都會讓那些輪次靜默沒有安撫話。
    assert set(acks.persona().generic) <= set(phrases)
    assert "好，我幫您看看最近的新聞喔" in phrases
