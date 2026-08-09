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


# ── 讀人設要看得見（2026-08-08 觀測盤點）──
#
# 人設與稱呼跑在 `PreparedTurn` 的第二條執行緒上，讀不到就靜默退回預設（見
# `PreparedTurn.profile` 的說明）。原本這次查詢在 Opik 一格都沒有——真的常常
# 逾時也不會有人知道，只會覺得「金孫最近怎麼不叫阿嬤了」。


def test_get_profile_is_its_own_span(monkeypatch):
    import opik

    from kinsun.accounts.profile import ElderProfile, ElderProfileReader
    from kinsun.tracing import client as tracing_client
    from kinsun.tracing import decorators as tracing_decorators

    names: list[str] = []
    monkeypatch.setattr(opik, "track", lambda **kw: (names.append(kw.get("name")), lambda f: f)[1])
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)
    monkeypatch.setattr(tracing_client, "_ENABLED", True)

    class _Store:
        def get_elder(self, elder_id):
            return None

    assert ElderProfileReader(_Store()).get_profile("e1") == ElderProfile()
    assert "elder_profile" in names
