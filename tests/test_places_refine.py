"""三道後處理。測試資料一律用 2026-07-27 實測撈到的真字串。"""

from __future__ import annotations

from kinsun.places.models import NearbyPlace, Place
from kinsun.places.refine import (
    _stem,
    dedupe,
    drop_suspicious_coordinates,
    refine,
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


def test_speakable_name_does_not_mangle_english_names_containing_line():
    """⚠️ 舊版 `_LINE_ID` 沒有詞界，`\\w+` 會吃進同一個英文單字裡「LINE」之後的字母。

    實測：「Skyline Cafe」被切成「Sky」、「Online Cafe」被切成「On」、
    「Shopline Cafe」被切成「Shop」、「Celine Hair」被切成「Ce」。
    """
    assert speakable_name("Skyline Cafe") == "Skyline Cafe"
    assert speakable_name("Online Cafe") == "Online Cafe"
    assert speakable_name("Shopline Cafe") == "Shopline Cafe"
    assert speakable_name("Celine Hair") == "Celine Hair"


def test_speakable_name_does_not_empty_out_real_line_branded_shops():
    """⚠️ 更嚴重的舊版行為：真實店名「LINE Cafe」「Line Tea」「Line Up綫髮藝」
    會被整串清成空字串，接著在 `refine()` 被靜默丟棄——長輩問附近有什麼，
    這幾家真實存在的手搖飲／髮廊會直接從答案裡消失。
    """
    assert speakable_name("LINE Cafe") == "LINE Cafe"
    assert speakable_name("Line Tea") == "Line Tea"
    assert speakable_name("Line Up綫髮藝") == "Line Up綫髮藝"


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
    got = drop_suspicious_coordinates([_n("沒有郵遞區號的店", 300, postcode=None)], [("235", 600)])
    assert len(got) == 1


def test_speakable_name_keeps_brand_hyphen():
    # 實測：7-ELEVEN／7-11 開頭全台 1,340 筆，英數字間帶連字號共 13,341 筆。
    # 超商是 categories.py 明訂的分類、密度全台最高，切成「7」會系統性發生。
    assert speakable_name("7-ELEVEN 石潭門市") == "7-ELEVEN 石潭門市"
    assert speakable_name("7-11湖慧門市~") == "7-11湖慧門市~"


def test_speakable_name_still_cuts_chinese_hyphen_suffix():
    assert speakable_name("斗六魷魚羹嘴羹-中和店") == "斗六魷魚羹嘴羹"


def test_speakable_name_never_returns_empty_for_separator_leading_names():
    # 實測全台 705 筆店名以分隔符開頭。回空字串等於把這家店從長輩的答案裡抹掉。
    assert speakable_name("【麵匠】麵食堂-彌陀總店") != ""
    assert speakable_name("(預約制)喜嫁六禮十二禮 禮俗用品") != ""


def test_dedupe_does_not_let_separator_leading_name_swallow_everything():
    """⚠️ 這條守的是一個會讓長輩收到空答案的 Critical，但**真正擋住它的不是這條測試**。

    2026-07-28 複審以突變證明：同時拿掉 `_stem` 的 fallback 與 `_same_shop` 的
    空字串守門，本檔 20 條測試照樣全綠——因為 `_MIN_STEM_FOR_CONTAINMENT` 的
    `shorter < 4` 早已擋下空主幹（長度 0 永遠過不了門檻），這條測試測到的其實是
    「短主幹去重門檻」而非「空主幹 fallback」。真正守住 fallback 的是
    `test_stem_never_returns_empty_for_separator_leading_names`（見下）。
    本測試仍保留：它守的是 dedupe 的最終行為（不因分隔符開頭的店名而誤刪鄰居），
    即使原因是門檻而非 fallback，這個行為本身仍值得測。
    """
    got = dedupe(
        [
            _n("【麵匠】麵食堂-彌陀總店", 10),
            _n("好安心藥局", 15),
            _n("全家福藥局", 20),
        ]
    )
    assert len(got) == 3


def test_stem_never_returns_empty_for_separator_leading_names():
    """真正守住 `_stem` 空字串 fallback 的測試（2026-07-28 補）。

    拿掉 `_stem` 的 fallback（`head or _STEM_CUT.sub("", cleaned).strip()` 改回
    只回傳 `head`）會讓這條測試變紅——已手動驗證過。
    """
    assert _stem("【麵匠】麵食堂-彌陀總店") != ""


def test_dedupe_keeps_short_name_and_longer_unrelated_shop():
    # 實測全台有 7,412 筆店名剛好兩個字（含「全家」）。沒有長度門檻時
    # 「全家」會被判定為「全家福小吃店」的重複而讓其中一家消失。
    got = dedupe([_n("全家", 10), _n("全家福小吃店", 15)])
    assert len(got) == 2


def test_refine_enforces_order_and_limit():
    """組合入口：剔除 → 去重 → 清洗 → 截斷，且截斷在最後。

    ⚠️ 這條測試的資料是刻意設計的，**兩種寫錯的實作都必須讓它失敗**——上一版寫得
    太鬆，複審員建了「截斷提前」與「順序對調」兩個壞版本，兩個都照樣通過，等於
    這條測試什麼都沒守住。設計如下：

    - 前兩筆是**同一家店**（主幹相同、相距約 22 公尺），近的那筆座標可疑、遠的正常。
      正確順序（先剔除）：可疑那筆先被拿掉，正常那筆留下。
      顛倒順序（先去重）：近的可疑筆當錨點把正常筆吃掉，接著自己被剔除 → **回空**。
    - `limit=2` 小於處理後的筆數。截斷若提前發生，可疑那筆會先佔掉一個名額，
      最後只剩一筆。
    """
    fingerprint = [("235", 600), ("112", 2)]
    got = refine(
        [
            # 近、但座標可疑（郵遞區號在鄰域佔比 0.3%）
            _n("宏益整復所", 100, postcode="112", lat=25.0),
            # 遠、座標正常；與上一筆相距約 22 公尺，屬同一家
            _n("宏益整復所", 200, postcode="235", lat=25.0002),
            _n("好安心藥局｜糖尿病照護、銀髮營養", 300),
            _n("力賀藥局LINE:@553oyqwx中和體重管理諮詢藥局", 400),
        ],
        fingerprint,
        limit=2,
    )
    assert [(s.name, s.distance_meters) for s in got] == [
        ("宏益整復所", 200),
        ("好安心藥局", 300),
    ]


def test_speakable_name_fallback_leaves_no_orphan_bracket():
    # fallback 是整串清理，只去左括號會留下孤兒「】」「)」，而這串字會進 TTS。
    assert speakable_name("【麵匠】麵食堂-彌陀總店") == "麵匠麵食堂彌陀總店"
    assert ")" not in speakable_name("(預約制)喜嫁六禮十二禮 禮俗用品")


def test_drop_suspicious_keeps_everything_when_fingerprint_too_small():
    # 鄰域樣本太少時佔比沒有意義（一筆就可能超過 2%），整道防線應停用而非亂殺。
    got = drop_suspicious_coordinates(
        [_n("a", 300, postcode="110"), _n("b", 400, postcode="112")], [("110", 3), ("112", 1)]
    )
    assert len(got) == 2
