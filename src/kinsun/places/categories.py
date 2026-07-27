"""長輩口語類別 → 查詢配方。新增類別＝在 CATEGORIES 加一列，不動其他檔案。

⚠️ 為什麼每一類都要「Overture 分類 OR 中文店名關鍵字」雙軌：Overture 的分類會錯標。
2026-07-27 實測撞到「百鮮鹹酥雞中和連城店」被標成 african_restaurant、
「層階抓漏-防水工程公司」被標成 pharmacy、埔里最近的「餐廳」第一名是網咖
「極地網際」。全庫 17% 筆數 confidence < 0.5。單靠分類會漏也會錯。

本表 15 類皆經 2026-07-27 五地實測（中和／信義／台中西屯／高雄三民／南投埔里），
1500 公尺內每地皆 ≥8 家。另有 12 類實測同樣全過但本輪未開（飲料店、火鍋、便當、
冰店、美容、美甲、五金行、教會、社區活動中心、ATM、廟口）——要開就是各加一列。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategorySpec:
    label: str  # 講給長輩聽的說法
    overture: tuple[str, ...] = ()  # 命中即納入的 Overture 分類值
    keywords: tuple[str, ...] = ()  # 命中即納入的中文店名關鍵字
    exclude: tuple[str, ...] = ()  # 命中即排除，優先於上面兩者
    label_note: str = ""  # 給維護者的備註，不進提示詞


CATEGORIES: dict[str, CategorySpec] = {
    "restaurant": CategorySpec(
        label="餐廳",
        overture=("restaurant",),
        keywords=("餐廳", "飯館", "食堂"),
        exclude=("網際", "網咖", "小吃部"),
    ),
    "snack": CategorySpec(
        label="小吃",
        overture=("delicatessen", "food_truck_stand", "diner"),
        keywords=(
            "小吃", "滷味", "臭豆腐", "水餃", "鹹酥雞", "鹽酥雞", "肉圓",
            "碗粿", "米糕", "蚵仔", "麵線", "刈包", "米粉", "擔仔",
        ),
        # 「小吃部」在南部是卡拉OK／酒店的代稱，與「小吃」只差一字。
        exclude=("小吃部",),
    ),
    "breakfast": CategorySpec(
        label="早餐店",
        overture=("breakfast_and_brunch_restaurant",),
        keywords=("早餐", "早午餐", "美而美", "蛋餅", "飯糰", "豆漿", "早點"),
    ),
    "noodles": CategorySpec(
        label="麵店",
        overture=("ramen_restaurant",),
        keywords=("拉麵", "牛肉麵", "麵館", "麵店", "麵攤", "意麵", "陽春麵"),
        exclude=("麵包", "製麵", "麵粉"),
    ),
    "cafe": CategorySpec(
        label="咖啡廳",
        overture=("coffee_shop", "cafe"),
        keywords=("咖啡", "珈琲"),
        exclude=("網咖", "internet"),
    ),
    "bakery": CategorySpec(
        label="麵包店",
        overture=("bakery",),
        keywords=("麵包", "烘焙", "西點"),
    ),
    "vegetarian": CategorySpec(
        label="素食",
        overture=("vegetarian_restaurant", "vegan_restaurant"),
        keywords=("素食", "蔬食", "素菜", "全素"),
        exclude=("酵素", "元素", "色素"),
    ),
    "pharmacy": CategorySpec(
        label="藥局",
        overture=("pharmacy",),
        keywords=("藥局", "藥房", "大藥局"),
        # 藥妝店不能調劑處方箋，長輩問「哪裡有藥局」多半是要領慢箋。
        # 實測 5,820 家藥局裡 1,493 家（25.7%）是這類。
        exclude=("屈臣氏", "Watsons", "康是美", "Cosmed", "日藥本舖", "藥妝", "藥粧", "抓漏"),
    ),
    "clinic": CategorySpec(
        label="診所",
        overture=("doctor", "medical_clinic"),
        keywords=("診所", "醫療社團法人", "聯合診所"),
        exclude=(
            "牙醫", "牙科", "齒科", "Dental", "dental",
            "整形", "美學", "醫學美容", "醫美", "減重", "瘦身", "植髮", "微整",
            "Aesthetic", "動物", "獸醫", "Veterinary",
        ),
    ),
    "chinese_medicine": CategorySpec(
        label="中醫",
        keywords=("中醫",),
        exclude=("美學", "美容", "瘦小臉"),
    ),
    "dentist": CategorySpec(
        label="牙醫",
        overture=("dentist",),
        keywords=("牙醫", "牙科", "齒科"),
        exclude=("動物", "獸醫"),
    ),
    "chiropractic": CategorySpec(
        label="推拿整復",
        # ⚠️ 這一類的納入詞刻意**不含**泛稱的「按摩」（Leo 核定 2026-07-27）。
        # 以「按摩／指壓／養生館／舒壓／SPA」查中和 1500 公尺得 56 筆，最近 25 筆裡
        # 真正符合長輩需求的只有 3 家，其餘是寵物 SPA、除毛美容，以及兩家
        # 「男女時尚舒壓會館」——台灣性產業的常用招牌。全台掃描：油壓 227 筆、
        # 舒壓 460 筆、茶室 88 筆、阿公店 25 筆。
        # 改用整復類配方後五地全部 ≥11 家，且回傳長相乾淨。
        label_note="長輩問「附近哪裡可以按摩」時用這一類",
        keywords=("整復", "整骨", "國術館", "推拿", "經絡", "筋絡", "傷科"),
        exclude=(
            "舒壓", "油壓", "指壓", "美容", "美睫", "除毛", "寵物",
            "做臉", "美甲", "會館", "護膚", "半套", "全套", "茶室", "阿公店",
        ),
    ),
    "hairdresser": CategorySpec(
        label="理髮店",
        overture=("hair_salon", "barber"),
        keywords=("理髮", "美髮", "髮廊", "剪髮", "髮型"),
    ),
    "convenience": CategorySpec(
        label="超商",
        overture=("convenience_store",),
        keywords=("7-ELEVEN", "統一超商", "全家", "萊爾富", "OK超商"),
    ),
    "temple": CategorySpec(
        label="廟",
        overture=("temple", "buddhist_temple", "taoist_temple"),
        keywords=("宮", "寺", "廟", "壇", "殿"),
        exclude=("廟口",),
    ),
}


def category_names() -> list[str]:
    """給 ToolSpec 的 enum 用。"""
    return list(CATEGORIES)


def matches(category: str, name: str, *, overture_category: str | None) -> bool:
    """這家店算不算這一類？排除詞優先於納入詞。

    排除詞必須先判、且一票否決：實測「琪淨美容美體館…經絡按摩…」同時含正面詞
    「經絡」與排除詞「美容」，若讓納入詞先贏，美容工作室就會被當成推拿館推給長輩。
    """
    spec = CATEGORIES.get(category)
    if spec is None:
        return False
    lowered = name.lower()
    if any(bad.lower() in lowered for bad in spec.exclude):
        return False
    if overture_category and overture_category in spec.overture:
        return True
    return any(good.lower() in lowered for good in spec.keywords)
