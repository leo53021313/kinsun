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
        "南華經絡養生館 Nanhua SPA",
    ],
)
def test_chiropractic_accepts_real_legitimate_shops(name):
    assert matches("chiropractic", name, overture_category=None)


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


def test_restaurant_accepts_by_overture_category_without_keywords():
    # 餐廳靠 Overture 分類就夠，店名不必含「餐廳」二字。
    assert matches("restaurant", "佐野拉麵", overture_category="restaurant")


def test_unknown_category_never_matches():
    assert not matches("massage", "隨便什麼店", overture_category="restaurant")
