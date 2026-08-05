"""ElderProfileReader：一次讀取同時供應人設與稱呼。

稱呼那一句的措辭與 2026-07-17 的 `ElderProfileFacts` **一字不差**，只是改成獨立
一行、不再包在 FactSection 裡。當時的實測背景：情境沒有任何稱呼資料時，模型每輪
自行猜一個性別稱謂（同一位長輩一下被叫阿公、一下被叫阿嬤），真實使用有一半機率
叫錯——所以這裡的兩條稱呼測試是回歸測試，不是新功能的測試。
"""

from __future__ import annotations

from kinsun.accounts.models import Elder
from kinsun.accounts.profile import ElderProfileReader
from kinsun.accounts.store import FakeAccountStore
from kinsun.personas import DEFAULT_PERSONA_ID, STEADY_GRANDSON


def _reader_for(elder: Elder | None) -> ElderProfileReader:
    store = FakeAccountStore()
    if elder is not None:
        store.save_elder(elder)
    return ElderProfileReader(store)


def test_unknown_elder_falls_back_to_default_persona_and_no_address():
    profile = _reader_for(None).get_profile("e-nope")
    assert profile.persona_id == DEFAULT_PERSONA_ID
    assert profile.address_line == ""


def test_nickname_is_used_verbatim():
    profile = _reader_for(Elder("e1", "王秀英", nickname="秀英阿嬤")).get_profile("e1")
    assert "秀英阿嬤" in profile.address_line


def test_name_fallback_forbids_gender_guessing():
    """稱謂未設定時退回名字，並明令不要猜「阿公／阿嬤」。"""
    line = _reader_for(Elder("e1", "王秀英")).get_profile("e1").address_line
    assert "王秀英" in line
    assert "不要" in line and "阿公" in line and "阿嬤" in line


def test_no_name_no_nickname_gives_empty_address_line():
    assert _reader_for(Elder("e1", "")).get_profile("e1").address_line == ""


def test_persona_is_carried_out():
    profile = _reader_for(Elder("e1", "王秀英", persona=STEADY_GRANDSON)).get_profile("e1")
    assert profile.persona_id == STEADY_GRANDSON


def test_unknown_persona_value_is_passed_through_untouched():
    """讀取器不做值域判斷——退回預設是 `personas.get_persona` 的職責，只有一處。"""
    profile = _reader_for(Elder("e1", "王秀英", persona="pirate_captain")).get_profile("e1")
    assert profile.persona_id == "pirate_captain"
