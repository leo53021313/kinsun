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
        resolve_place=lambda q: (25.0425, 121.507) if "西門" in q else None,
    )


def _place(name: str, lat: float, lon: float, category="chiropractic", **kw) -> Place:
    return Place(
        place_id=f"{name}",
        name=name,
        latitude=lat,
        longitude=lon,
        category=category,
        ingested_at=1753600000.0,
        **kw,
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
    handler = _wire([_place("余宗益調理整復所", 25.0025, 121.5)], recorded_at=NOW - 3 * 3600)
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


def test_place_too_far_from_elder_is_refused():
    """模型把店名當地名傳進來時，不可直接報那邊的店（2026-07-28 端到端實測抓到）。

    實測 Nominatim 對店名照單全收：「麥當勞」解析到台南、離中和 254 公里。
    沒有這道護欄，長輩說「我想吃麥當勞」會收到一串台南的店、而句子裡寫著「附近」。
    """
    place_store = FakePlaceStore()
    place_store.save_many([_place("台南的店", 23.047, 120.188, category="restaurant")])
    locations = FakeLocationStore()
    locations.save(ElderLocation(ELDER, "中和區", NOW, 25.0, 121.5))
    handler = build_nearby_handler(
        place_store,
        locations,
        clock=lambda: NOW,
        stale_after_hours=2,
        resolve_place=lambda q: (23.047, 120.188),  # 台南
    )
    out = handler(
        {"category": "restaurant", "place": "麥當勞"},
        ToolInvocationContext("t", ELDER, False),
    )
    assert "台南的店" not in out
    assert "太遠" in out


def test_place_within_same_area_is_allowed():
    """「西門町附近有什麼吃的」是合法用法，離中和 4.9 公里，護欄不可誤擋。"""
    handler = _wire([_place("西門町的店", 25.0425, 121.507, category="restaurant")])
    out = handler(
        {"category": "restaurant", "place": "西門町"},
        ToolInvocationContext("t", ELDER, False),
    )
    assert "西門町的店" in out


def test_place_center_is_named_in_the_output():
    """中心點不是長輩所在地時，回傳字串必須講出來。

    ⚠️ 原本無論中心點在哪都寫死「附近的餐廳：」，於是模型把別區的店講成「附近」，
    而它沒有任何線索知道該改口——工具沒告訴它中心點被換過。
    """
    handler = _wire([_place("西門町的店", 25.0425, 121.507, category="restaurant")])
    out = handler(
        {"category": "restaurant", "place": "西門町"},
        ToolInvocationContext("t", ELDER, False),
    )
    assert out.startswith("西門町附近的")


def test_own_location_output_says_plain_nearby():
    """沒填 place 時維持原本的「附近的…」措辭，不要多出地名。"""
    handler = _wire([_place("余宗益調理整復所", 25.0025, 121.5)])
    out = handler({"category": "chiropractic"}, ToolInvocationContext("t", ELDER, False))
    assert out.startswith("附近的")


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
                25.0025,
                121.5,
                category="pharmacy",
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


def test_blank_elder_id_in_context_means_no_query():
    """context 在但 elder_id 是空字串——與 context=None 同樣不可查。

    這條與下面那條合起來封住「不知道是誰在講話卻仍去查位置」的兩種入口。

    ⚠️ 位置刻意註冊在空字串這個 key 底下，而非沿用 `_wire()` 預設的 ELDER
    （2026-07-27 覆核時發現並修正）：若沿用 `_wire()`，`locations.get_for_elder("")`
    本來就查無此人、落回「不知道長輩在哪裡」，就算把 elder_id 的守門條件整段拿掉，
    這條測試依然通過——測不出守門條件到底有沒有生效。位置準備在同一把 key 下，
    才是真的在單獨測「拿掉 elder_id 守門」這件事。
    """
    place_store = FakePlaceStore()
    place_store.save_many([_place("余宗益調理整復所", 25.0025, 121.5)])
    locations = FakeLocationStore()
    locations.save(ElderLocation("", "中和區", NOW, 25.0, 121.5))
    handler = build_nearby_handler(
        place_store,
        locations,
        clock=lambda: NOW,
        stale_after_hours=2,
        resolve_place=lambda q: None,
    )
    out = handler({"category": "chiropractic"}, ToolInvocationContext("t", "", False))
    assert "余宗益調理整復所" not in out


def test_location_without_coordinates_asks_instead_of_guessing():
    """位置有地名但沒有座標——這是正式資料裡真實存在的情形。

    `locations/store.py` 檔頭載明：PR #55 寫入的既有列沒有座標（ALTER 後為 NULL）。
    那些列的 `place` 有值、`latitude`／`longitude` 是 None。此時必須開口問，
    絕不可拿地名去猜座標——猜錯會把長輩指到別的城市。
    """
    place_store = FakePlaceStore()
    place_store.save_many([_place("余宗益調理整復所", 25.0025, 121.5)])
    locations = FakeLocationStore()
    locations.save(ElderLocation(ELDER, "中和區", 1753600000.0))  # 只有地名，無座標
    handler = build_nearby_handler(
        place_store,
        locations,
        clock=lambda: NOW,
        stale_after_hours=2,
        resolve_place=lambda q: None,
    )
    out = handler({"category": "chiropractic"}, ToolInvocationContext("t", ELDER, False))
    assert "余宗益調理整復所" not in out


def test_no_context_means_no_query():
    handler = _wire([_place("余宗益調理整復所", 25.0025, 121.5)])
    out = handler({"category": "chiropractic"}, None)
    assert "余宗益調理整復所" not in out


def test_unresolvable_place_echo_is_truncated_and_has_no_newlines():
    """⚠️ 工具回傳原封回顯模型傳來的 place，無長度上限（2026-07-28 審查發現）。

    實測傳一個含換行、300 字的 place，整串原封出現在工具回傳開頭，會把真正的店家
    清單擠出 registry.py 的 2000 字截斷視窗。修法是限長＋去換行，不是不回顯。
    """
    handler = _wire([_place("余宗益調理整復所", 25.0025, 121.5)])
    long_place = ("壞\n心\n地\n名" * 100) + "但西門沒有出現在這裡"
    out = handler(
        {"category": "chiropractic", "place": long_place},
        ToolInvocationContext("t", ELDER, False),
    )
    assert "\n" not in out
    assert len(out) < 100


def test_place_too_far_echo_is_truncated_and_has_no_newlines():
    place_store = FakePlaceStore()
    place_store.save_many([_place("台南的店", 23.047, 120.188, category="restaurant")])
    locations = FakeLocationStore()
    locations.save(ElderLocation(ELDER, "中和區", NOW, 25.0, 121.5))
    handler = build_nearby_handler(
        place_store,
        locations,
        clock=lambda: NOW,
        stale_after_hours=2,
        resolve_place=lambda q: (23.047, 120.188),  # 台南
    )
    long_place = "麥當勞" * 100 + "\n換行還在這裡"
    out = handler(
        {"category": "restaurant", "place": long_place},
        ToolInvocationContext("t", ELDER, False),
    )
    assert "太遠" in out
    assert "\n" not in out
    assert len(out) < 150


def test_place_center_label_echo_is_truncated_in_success_message():
    """中心點仍要講出來（不可拿掉），但回顯的地名本身要限長。"""
    handler = _wire([_place("西門町的店", 25.0425, 121.507, category="restaurant")])
    long_place = "西門" + "很長的地名描述" * 50 + "\n多一行也不該出現"
    out = handler(
        {"category": "restaurant", "place": long_place},
        ToolInvocationContext("t", ELDER, False),
    )
    assert "\n" not in out
    assert "西門町的店" in out
    assert len(out) < 200
