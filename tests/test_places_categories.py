"""類別對照：守住「長輩口語 → 查詢配方」的對應，以及 chiropractic 的安全界線。

反例一律用 2026-07-27 實測撈到的**真店名**。自己編的假資料不會有真實資料的形狀
——「Chill男女時尚舒壓會館」這種名字編不出來，而它正是要擋的東西。
"""

from __future__ import annotations

import pytest

from kinsun.places.categories import CATEGORIES, category_names, matches


def test_all_categories_have_a_spoken_label():
    for code, spec in CATEGORIES.items():
        assert spec.label, f"{code} 缺少長輩看得懂的中文標籤"


def test_category_names_are_the_enum_for_the_tool_spec():
    names = category_names()
    assert "restaurant" in names
    assert "chiropractic" in names
    # 泛稱的「按摩」刻意不存在（Leo 核定 2026-07-27）——實測撈出的多為性產業與寵物 SPA。
    assert "massage" not in names


@pytest.mark.parametrize(
    "name",
    [
        "余宗益調理整復所",
        "龍飛國術館",
        "不二堂正骨整復",
        "陳師父推拿",
    ],
)
def test_chiropractic_accepts_real_legitimate_shops(name):
    assert matches("chiropractic", name, overture_category=None)


# ⚠️ 「南華經絡養生館 Nanhua SPA」（2026-07-28 審查發現，Leo 待確認）：原本列在上面
# 的必收清單，但複審指出它與下面 `test_chiropractic_會館_排除詞...` 擋的「艾沐經絡
# 美學會館」是同一種店（對正式庫查證：taxonomy.primary='spa'，Overture 自己就把它歸
# 類成 spa），兩條測試對同一類店立場相反，故先移出必收清單。
# 但**沒有跟著移進必擋清單**：試過用「SPA」（英文）當排除詞會連帶擋掉一筆真正的
# 整復店——「Rock專業整復推拿 SPA」（taxonomy.primary='chiropractic'，Overture 自己
# 標成合法整復），代表店名含「SPA」不是乾淨信號，會誤殺；試過用「養生館」當排除詞
# collateral 更大——53 筆含「養生館」仍會通過現有規則，其中「張師父整復養生館」
# 「老裕元整復中心國術館養生館」都是 Overture 標成 chiropractic 的合法整復館。
# 兩種文字關鍵字都會製造新的假陰性，與本檔既有先例（「會館」全台 40 家絕大多數
# 係誤配才收）不符——這筆的「壞」佔比只有約六成，不到「絕大多數」的門檻。
# 真正乾淨的做法會是用 Overture 分類本身當排除信號（例如 taxonomy_primary in
# {"spa","beauty_salon","personal_or_beauty_service","aromatherapy",
# "skin_care_and_makeup","hair_removal"} 時一票否決），但那是 `matches()` 目前沒有
# 的新機制（現有排除只認店名關鍵字），屬於比這輪修復更大的變更，故本輪不做、
# 留給下一個人接手；此店暫不進兩份清單。
@pytest.mark.parametrize(
    "name",
    [
        "Chill男女時尚舒壓會館",
        "晶采夢男女時尚舒壓會館",
        "老師傅專業舒壓家",
        "Q&Do寵物SPA沙龍",
        "慕時光·Skin care & spa｜韓式肌膚管理｜私密處Vio無痛除毛｜精油芳療按摩",
        "琪淨美容美體館-新北永和中和做臉｜手工清粉刺肉芽｜經絡按摩｜霧眉",
    ],
)
def test_chiropractic_rejects_real_unwanted_shops(name):
    # 最後一筆是刻意的邊界案例：名字裡有「經絡」（正面詞）但同時有「美容」「做臉」，
    # 排除詞必須勝過納入詞，否則美容工作室會被當成推拿館推給長輩。
    assert not matches("chiropractic", name, overture_category=None)


def test_chiropractic_會館_排除詞_必須_攔住_美容spa():
    """艾沐經絡美學會館是真實案例（全台 40 家類似店）。

    含納入詞「經絡」✓、不含「舒壓」「油壓」「美容」⚠️ 都不含，只有「美學」（不是「美容」）。
    但排除詞「會館」必須一票否決——她是美容／SPA 會館，不是長輩要的推拿館。

    這條測試駁斥審查員的異議「永和國術會館」不存在——實測全台 40 家命中者絕大多數正是要擋的。
    """
    assert not matches("chiropractic", "艾沐經絡美學會館", overture_category=None)


def test_chiropractic_正規化_全形與夾空格():
    """排除詞能被全形字與夾空格繞過，是安全漏洞。

    `str.lower()` 不處理全形字元，也擋不住「舒 壓」這種夾空格的寫法。
    正規化後須能擋住：全形舒壓、夾空格舒壓、全形加空格的組合。
    """
    # 全形舒壓（實測真的有店用全形）
    assert not matches("chiropractic", "半天堂推拿舒壓院", overture_category=None)

    # 夾空格舒壓
    assert not matches("chiropractic", "半天堂推拿舒 壓院", overture_category=None)

    # 混合全形空格與全形標點（常見於商家名）
    assert not matches("chiropractic", "半天堂推拿　舒壓　院", overture_category=None)


def test_clinic_matches_new_taxonomy_overture_values():
    # 2026-07-27 對正式庫查證：舊值 doctor／medical_clinic 是死碼（0 筆）。
    assert matches("clinic", "隨便診所", overture_category="doctors_office")


def test_dentist_matches_dental_clinic_overture_value():
    # 舊值 dentist 在正式庫 0 筆，新 taxonomy 已更名為 dental_clinic。
    assert matches("dentist", "TISS Dental Implant", overture_category="dental_clinic")


def test_temple_matches_buddhist_place_of_worship_but_not_church():
    # 只收佛教這一個值：christian_place_of_worship 是教會，長輩問廟答非所問。
    assert matches("temple", "濟緣堂", overture_category="buddhist_place_of_worship")
    assert not matches("temple", "主愛教會", overture_category="christian_place_of_worship")


def test_temple_excludes_huatan_township_name():
    # 「壇」這個單字關鍵字會把彰化縣花壇鄉整個地名收進來（實測 251 筆），
    # 例如「三媽臭臭鍋花壇店」「CJ E-bike 電動車 花壇店」——與宗教場所無關。
    assert not matches("temple", "三媽臭臭鍋花壇店", overture_category=None)


def test_temple_exclude_overture_vetoes_japanese_restaurant_chain():
    """勝博殿是全台連鎖日式豬排店，店名關鍵字「殿」擋不住（殿本身是納入詞）。

    2026-07-28 對正式庫查證：taxonomy_primary='japanese_restaurant' 的 97 筆命中
    裡，category_alternate 查無任何一筆帶宗教／古蹟殘留信號，判斷安全可排除。
    """
    assert not matches("temple", "勝博殿", overture_category="japanese_restaurant")
    # 沒有 Overture 分類佐證時（例如查詢端沒帶分類），仍靠關鍵字後援收進來。
    assert matches("temple", "勝博殿", overture_category=None)


def test_temple_exclude_overture_vetoes_food_truck_and_beauty_salon():
    """真店名：「深夜冷宮」是滷味攤（food_truck_stand），「美睫殿の小屋」是美睫店
    （beauty_salon）。兩者都不含既有的店名排除詞（廟口／飯店／酒店…），只能靠
    Overture 分類本身擋下。
    """
    assert not matches("temple", "深夜冷宮｜冷盤｜涼拌小菜", overture_category="food_truck_stand")
    assert not matches("temple", "美睫殿の小屋", overture_category="beauty_salon")


def test_temple_exclude_overture_does_not_veto_ambiguous_categories():
    """historic_site／palace 等分類是歧義的（龍山寺、行天宮本來就同時是古蹟），
    2026-07-28 審查刻意不放進 exclude_overture，這裡守住「不可誤加」的界線。
    """
    assert matches("temple", "龍山寺", overture_category="historic_site")
    assert matches("temple", "行天宮", overture_category="palace")


def test_temple_exclude_overture_does_not_veto_lodging_despite_task_brief():
    """⚠️ 這條測試守的是本輪最重要的修正：不可依原任務書把 lodging 加進排除清單。

    對正式庫查證：taxonomy_primary='lodging' 且命中廟關鍵字的 244 筆裡，236 筆
    （96.7%）店名完全沒有任何旅宿字樣、是純廟名；其中「北港朝天宮 厚生大樓」
    （北港朝天宮本尊的附屬建物）category_alternate 直接帶 religious_organization，
    confidence 0.90。若把 lodging 加進 exclude_overture，這座全台知名度數一數二
    的媽祖廟會從「附近有廟」查詢中消失——代價遠高於漏擋幾家旅宿，故拒絕加入。
    """
    assert matches("temple", "北港朝天宮 厚生大樓", overture_category="lodging")
    assert matches("temple", "宜蘭東嶽廟", overture_category="restaurant")
    assert matches("temple", "埔心武聖宮", overture_category="delicatessen")


def test_pharmacy_requires_keyword_even_when_overture_category_matches():
    """⚠️ 這條守住 C-2 的 Critical：Overture 的 pharmacy 分類單獨不可信。

    實測「附近有藥局嗎」第一名查到「元大銀行中和分行」（overture_category='pharmacy'，
    距長輩僅 106 公尺）。改成 require_keyword=True 後，Overture 分類命中但店名沒有
    藥局關鍵字的店必須被擋下，不能再靠分類單軌進榜。
    """
    assert not matches("pharmacy", "元大銀行中和分行", overture_category="pharmacy")
    # 有關鍵字的藥局，Overture 分類命中與否都應該收。
    assert matches("pharmacy", "力賀藥局", overture_category="pharmacy")
    assert matches("pharmacy", "力賀藥局", overture_category=None)


def test_convenience_matches_fullwidth_and_halfwidth_hyphen_variant():
    """⚠️ NFKC 正規化是承重的，但一直沒有測試守住（2026-07-28 補）。

    正式庫真實存在「7－11萬芳門市」這種用全形連字號（U+FF0D）的店名，靠 NFKC
    轉半形才能命中「7-11」關鍵字。拿掉 `_normalized` 裡的 NFKC 正規化，只做
    去空白，這條會變紅——已手動驗證過。
    """
    assert matches("convenience", "７－１１萬芳門市", overture_category=None)


@pytest.mark.parametrize("name", ["全家旅店", "全家眼鏡公司-中和店"])
def test_convenience_rejects_同名非超商行業(name):
    # 「全家」太寬：2026-07-27 灌入後實查撈到旅館與眼鏡行，長輩問超商被回一家旅館。
    assert not matches("convenience", name, overture_category=None)


def test_convenience_accepts_full_brand_name():
    assert matches("convenience", "全家便利商店-中和莒光店", overture_category=None)


def test_restaurant_accepts_by_overture_category_without_keywords():
    # 餐廳靠 Overture 分類就夠，店名不必含「餐廳」二字。
    assert matches("restaurant", "佐野拉麵", overture_category="restaurant")


def test_unknown_category_never_matches():
    assert not matches("massage", "隨便什麼店", overture_category="restaurant")
