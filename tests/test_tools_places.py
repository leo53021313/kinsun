"""附近地點工具。重點守住座標來源的三條界線與後處理有真的被套上。"""

from __future__ import annotations

from kinsun.locations.store import ElderLocation, FakeLocationStore
from kinsun.places.models import Place
from kinsun.places.store import FakePlaceStore
from kinsun.tools.places import NEARBY_SPEC, build_nearby_handler
from kinsun.tools.registry import ToolInvocationContext

ELDER = "e-1"


NOW = 1753600060.0


def _wire(places: list[Place], *, located: bool = True, recorded_at: float = 1753600000.0):
    place_store = FakePlaceStore()
    place_store.save_many(places)
    locations = FakeLocationStore()
    if located:
        locations.save(ElderLocation(ELDER, "中和區", recorded_at, 25.0, 121.5))
    return build_nearby_handler(
        place_store,
        locations,
        clock=lambda: NOW,
        stale_after_hours=2,
        # 假地理編碼：只認得「西門町」，其餘一律查不到——測試不碰網路。
        resolve_place=lambda q: (25.042, 121.507) if "西門" in q else None,
    )


def _place(name: str, lat: float, lon: float, category="chiropractic", **kw) -> Place:
    return Place(
        place_id=f"{name}", name=name, latitude=lat, longitude=lon,
        category=category, ingested_at=1753600000.0, **kw
    )


def test_spec_enumerates_categories_and_requires_category():
    assert NEARBY_SPEC.name == "search_nearby_places"
    props = NEARBY_SPEC.parameters["properties"]
    assert "restaurant" in props["category"]["enum"]
    assert NEARBY_SPEC.parameters["required"] == ["category"]


def test_returns_nearby_shops_with_distance():
    handler = _wire([_place("余宗益調理整復所", 25.0025, 121.5)])
    out = handler({"category": "chiropractic"}, ToolInvocationContext("t", ELDER, False))
    assert "余宗益調理整復所" in out


def test_elder_id_from_model_is_ignored():
    """⚠️ 跨帳號外洩防線：模型傳 elder_id 進來一律不採用。

    此路已由 2026-07-17-長輩目前地點-design.md 封死——模型會幻覺，也可能被長輩的
    話術帶偏，結果是查到別位長輩的位置。本測試守住它不被日後「順手加個參數」打開。
    """
    handler = _wire([_place("余宗益調理整復所", 25.0025, 121.5)])
    out = handler(
        {"category": "chiropractic", "elder_id": "別人的-id"},
        ToolInvocationContext("t", ELDER, False),
    )
    assert "余宗益調理整復所" in out


def test_asks_when_location_unknown():
    handler = _wire([_place("余宗益調理整復所", 25.0025, 121.5)], located=False)
    out = handler({"category": "chiropractic"}, ToolInvocationContext("t", ELDER, False))
    assert "余宗益調理整復所" not in out
    # 不猜、不用預設城市，回一句讓模型開口問的話。
    assert "哪" in out or "位置" in out


def test_asks_when_location_is_stale():
    """過期的位置比沒有位置更糟：與其很有自信地報錯一個城市的店家，不如照舊開口問。

    門檻 2 小時＝LOCATION_STALE_AFTER_HOURS，與 LocationFacts 共用同一個設定。
    """
    handler = _wire(
        [_place("余宗益調理整復所", 25.0025, 121.5)], recorded_at=NOW - 3 * 3600
    )
    out = handler({"category": "chiropractic"}, ToolInvocationContext("t", ELDER, False))
    assert "余宗益調理整復所" not in out


def test_place_parameter_overrides_elder_location():
    """長輩問「西門町附近有什麼吃的」——中心點換成他問的地方，不是他站著的地方。"""
    handler = _wire([_place("西門町的店", 25.0425, 121.507, category="restaurant")])
    out = handler(
        {"category": "restaurant", "place": "西門町"},
        ToolInvocationContext("t", ELDER, False),
    )
    assert "西門町的店" in out


def test_unresolvable_place_asks_instead_of_falling_back():
    """地名查不到就問清楚，**不可**默默退回長輩目前位置——那會答非所問而且沒人發現。"""
    handler = _wire([_place("長輩家附近的店", 25.0025, 121.5, category="restaurant")])
    out = handler(
        {"category": "restaurant", "place": "不存在的地方"},
        ToolInvocationContext("t", ELDER, False),
    )
    assert "長輩家附近的店" not in out


def test_says_not_found_without_widening_radius():
    # 2.9 公里外的板橋分店不可被撈出來——放大半徑會把長輩指去板橋。
    handler = _wire([_place("小高拉麵", 25.026, 121.5, category="noodles")])
    out = handler({"category": "noodles"}, ToolInvocationContext("t", ELDER, False))
    assert "小高拉麵" not in out


def test_output_is_cleaned_and_warns_about_opening_hours():
    handler = _wire(
        [
            _place(
                "好安心藥局｜糖尿病照護、銀髮營養、健保特約藥局",
                25.0025, 121.5, category="pharmacy",
            )
        ]
    )
    out = handler({"category": "pharmacy"}, ToolInvocationContext("t", ELDER, False))
    assert "好安心藥局" in out
    assert "糖尿病照護" not in out
    # operating_status 實測 923,241/923,297 為 NULL，我們無法排除已歇業——
    # 必須讓模型知道，它才講得出「要不要先打個電話問問」。
    assert "開" in out


def test_unknown_category_is_rejected_without_echoing_input():
    """模型亂造類別時要擋，而且**不可回顯它給的字串**。

    工具回傳會整段進模型 context，最壞的情況是金孫照著唸給長輩聽——
    registry.py 對例外訊息只回類型名不回原文，是同一個理由。
    """
    handler = _wire([])
    out = handler({"category": "massage"}, ToolInvocationContext("t", ELDER, False))
    assert "massage" not in out
    assert "沒有這一類" in out


def test_no_context_means_no_query():
    handler = _wire([_place("余宗益調理整復所", 25.0025, 121.5)])
    out = handler({"category": "chiropractic"}, None)
    assert "余宗益調理整復所" not in out
