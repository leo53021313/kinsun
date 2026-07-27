"""三道後處理。測試資料一律用 2026-07-27 實測撈到的真字串。"""

from __future__ import annotations

from kinsun.places.models import NearbyPlace, Place
from kinsun.places.refine import (
    dedupe,
    drop_suspicious_coordinates,
    speakable_name,
)


def _n(name: str, meters: int, postcode: str | None = "235", lat=25.0, lon=121.5) -> NearbyPlace:
    return NearbyPlace(
        Place(
            place_id=f"{name}{meters}",
            name=name,
            latitude=lat,
            longitude=lon,
            category="chiropractic",
            postcode=postcode,
        ),
        meters,
    )


# ── 店名清洗 ──────────────────────────────────────────────


def test_speakable_name_cuts_at_first_separator():
    raw = "好安心藥局｜糖尿病照護、銀髮營養、健保特約藥局、專業處方調劑、戒菸服務"
    assert speakable_name(raw) == "好安心藥局"


def test_speakable_name_strips_seo_symbols():
    raw = "景安大澤藥局★處方調劑☆藥物保健諮詢★長照2.0諮詢☆輔具及無障礙空間補助申請"
    assert speakable_name(raw) == "景安大澤藥局"


def test_speakable_name_strips_line_id():
    raw = "力賀藥局LINE:@553oyqwx中和體重管理諮詢藥局"
    assert "LINE" not in speakable_name(raw)
    assert "553oyqwx" not in speakable_name(raw)


def test_speakable_name_cuts_parenthetical_notice():
    assert speakable_name("夏爾診所(即日起搬遷至隔壁56號!!!!)") == "夏爾診所"


def test_speakable_name_truncates_long_names():
    raw = "和川堂骨脈整復平衡預約制傳統按摩整復推拿刮痧拔罐養身保健產後調理正蓇整脊"
    assert len(speakable_name(raw)) <= 15


def test_speakable_name_leaves_clean_names_alone():
    assert speakable_name("余宗益調理整復所") == "余宗益調理整復所"
    assert speakable_name("龍飛國術館") == "龍飛國術館"


# ── 去重 ──────────────────────────────────────────────


def test_dedupe_removes_same_shop_listed_twice():
    # 實測：埔里同一家整復所被收錄兩次，相距 2 公尺。
    got = dedupe([_n("宏益整復所", 401), _n("埔里按摩推拿整復-宏益整復所", 403)])
    assert [n.place.name for n in got] == ["宏益整復所"]


def test_dedupe_keeps_different_shops_in_the_same_building():
    # ⚠️ 這條守住最容易寫錯的方向：中和 1.5 公里內「40 公尺內同類」的配對有 3,684 對，
    # 但店名高度相似者 0 對——那些全是同一棟樓或美食街裡的不同店家。
    # 只用距離去重會把整條小吃街刪成一家。
    got = dedupe([_n("斗六魷魚羹", 200), _n("滷味天城", 205), _n("牟家水餃", 210)])
    assert len(got) == 3


def test_dedupe_keeps_same_name_far_apart():
    # 連鎖店的不同分店不是重複。
    # ⚠️ 必須明確給不同座標：`_n` 的 lat/lon 有預設值，而 dedupe 是用**座標**算距離
    # （`meters` 參數只是相對查詢點的距離，不是兩店之間的距離）。兩筆都用預設座標
    # 等於兩家店疊在同一點，這條測試就測不到「遠」這件事。25.0126 約在 25.0 以北 1.4 公里。
    got = dedupe([_n("龍飛國術館", 300), _n("龍飛國術館", 1400, lat=25.0126)])
    assert len(got) == 2


# ── 座標可疑剔除 ──────────────────────────────────────────────


def test_drop_suspicious_removes_out_of_district_row():
    # 實測：北投的 112 在信義區鄰域佔 0.02%，遠低於 2% 門檻。
    fingerprint = [("110", 7696), ("106", 4023), ("112", 2)]
    got = drop_suspicious_coordinates(
        [_n("正常店", 300, postcode="110"), _n("台北榮總", 1129, postcode="112")],
        fingerprint,
    )
    assert [n.place.name for n in got] == ["正常店"]


def test_drop_suspicious_keeps_boundary_districts():
    # 中和與台北市相鄰，交界處的合法結果不可被誤殺——故用佔比而非「等於眾數」。
    fingerprint = [("235", 600), ("234", 300), ("116", 100)]
    got = drop_suspicious_coordinates(
        [_n("中和的店", 300, postcode="235"), _n("文山的店", 900, postcode="116")],
        fingerprint,
    )
    assert len(got) == 2


def test_drop_suspicious_keeps_rows_without_postcode():
    # 已知漏網率約 8.6%：沒有郵遞區號就無從判斷，此時保留而非剔除——
    # 誤殺合法結果的代價高於放行一筆可能錯位的。
    got = drop_suspicious_coordinates(
        [_n("沒有郵遞區號的店", 300, postcode=None)], [("235", 600)]
    )
    assert len(got) == 1


def test_drop_suspicious_keeps_everything_when_fingerprint_too_small():
    # 鄰域樣本太少時佔比沒有意義（一筆就可能超過 2%），整道防線應停用而非亂殺。
    got = drop_suspicious_coordinates(
        [_n("a", 300, postcode="110"), _n("b", 400, postcode="112")], [("110", 3), ("112", 1)]
    )
    assert len(got) == 2
