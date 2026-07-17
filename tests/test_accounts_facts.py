"""ElderProfileFacts：把稱謂（或名字保底）注入情境，杜絕模型亂猜「阿公／阿嬤」。

2026-07-17 全功能測試實測：情境沒有任何稱呼資料時，模型每輪自行猜一個性別稱謂
（同一長輩一下被叫阿公、一下被叫阿嬤），真實使用有一半機率叫錯。
"""

from kinsun.accounts.facts import ElderProfileFacts
from kinsun.accounts.models import Elder
from kinsun.accounts.store import FakeAccountStore


def _facts_for(elder: Elder | None) -> ElderProfileFacts:
    store = FakeAccountStore()
    if elder is not None:
        store.save_elder(elder)
    return ElderProfileFacts(store)


def test_unknown_elder_returns_none():
    assert _facts_for(None).facts("e-nope") is None


def test_nickname_is_injected_verbatim():
    section = _facts_for(Elder("e1", "王秀英", nickname="秀英阿嬤")).facts("e1")
    assert section is not None
    assert any("秀英阿嬤" in item for item in section.items)


def test_name_fallback_forbids_gender_guessing():
    """稱謂未設定時退回名字，並明令不要猜「阿公／阿嬤」。"""
    section = _facts_for(Elder("e1", "王秀英")).facts("e1")
    assert section is not None
    joined = "".join(section.items)
    assert "王秀英" in joined
    assert "不要" in joined and "阿公" in joined and "阿嬤" in joined


def test_no_name_no_nickname_returns_none():
    assert _facts_for(Elder("e1", "")).facts("e1") is None
