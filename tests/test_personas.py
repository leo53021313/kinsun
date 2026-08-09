"""人設目錄的守門測試。

最重要的一條是 `test_tone_never_names_a_tool`：`composition.py` 靠字面掃描
`agent.SYSTEM_PROMPT` 對帳「提示詞點名的工具有沒有註冊」，工具名一旦搬進人設段
那道對帳就會失效（提示詞講了某個工具、但沒有人發現它其實沒註冊）。掃描手法照抄
`tests/test_speech_acks.py`——走遍 kinsun.tools 蒐集模組級 ToolSpec，新增工具檔
會自動納入，不需要有人記得回來更新這份測試。
"""

from __future__ import annotations

import importlib
import pkgutil

import pytest

import kinsun.tools as tools_pkg
from kinsun import personas
from kinsun.llm import ToolSpec


def _registered_tool_names() -> set[str]:
    names: set[str] = set()
    for module_info in pkgutil.iter_modules(tools_pkg.__path__):
        module = importlib.import_module(f"{tools_pkg.__name__}.{module_info.name}")
        names |= {value.name for value in vars(module).values() if isinstance(value, ToolSpec)}
    return names


def test_catalogue_is_not_empty_and_default_is_registered():
    assert personas.DEFAULT_PERSONA_ID in personas.persona_ids()
    assert len(personas.persona_ids()) == 2


@pytest.mark.parametrize("persona_id", personas.persona_ids())
def test_each_persona_is_self_consistent(persona_id: str):
    one = personas.get_persona(persona_id)
    assert one.persona_id == persona_id
    assert one.label.strip()
    assert one.tone.strip()


@pytest.mark.parametrize("bad", ["", "  ", "nope", "KINSUN"])
def test_unknown_falls_back_to_default(bad: str):
    """讀取寬容：資料庫裡存了認不得的值時，長輩仍要能正常對話。"""
    assert personas.get_persona(bad).persona_id == personas.DEFAULT_PERSONA_ID


def test_tool_scan_actually_finds_tools():
    """先證明掃描有偵測力——掃不到東西的話，下面那條會空轉通過。"""
    found = _registered_tool_names()
    assert len(found) >= 10, f"只掃到 {len(found)} 個工具，掃描邏輯可能壞了"


def test_tone_never_names_a_tool():
    """⭐ 工具名只能住在規則段（見本檔 docstring）。"""
    tools = _registered_tool_names()
    for persona_id in personas.persona_ids():
        tone = personas.get_persona(persona_id).tone
        named = sorted(name for name in tools if name in tone)
        assert not named, f"人設 {persona_id} 的語氣段落點名了工具：{named}"


def test_tone_does_not_claim_to_be_a_real_family_member():
    """人設只管語氣，不得抵觸規則段的「你是 AI，不要假裝是真人或家人」。

    ⚠️ 這條是回歸測試（2026-08-05 真模型探針）：初版的 tone 寫「把這位長輩當成
    自己的阿公阿嬤在陪伴」，長輩問「你知道我是誰嗎」時兩種人設都把它當事實複述
    ——「您是我的阿嬤啊」。措辭一旦像在陳述關係，模型就會照著講。
    """
    for persona_id in personas.persona_ids():
        tone = personas.get_persona(persona_id).tone
        assert "真的孫" not in tone
        assert "不是 AI" not in tone
        # 親屬稱謂只能出現在明講是比喻的句子裡（「口吻像個…孫女」），不可用來
        # 陳述金孫與這位長輩的關係。
        assert "當成自己的阿公阿嬤" not in tone
        assert "你的阿嬤" not in tone and "你的阿公" not in tone
