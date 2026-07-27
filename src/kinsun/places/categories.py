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

import re
import unicodedata
from dataclasses import dataclass

_SPACES = re.compile(r"\s+")


def _normalized(text: str) -> str:
    """比對用的正規化字串：全形轉半形、去空白、轉小寫。

    ⚠️ 這不是美化，是安全需求。chiropractic 的排除詞擋的是性產業招牌，而
    `str.lower()` 不處理全形字元、也擋不住「舒 壓」這種夾空格的寫法。
    中文商家名用全形標點與空白極為常見，不正規化等於把防線留一道門。
    回傳值只用於比對，不改動 `name` 原值——那是要唸給長輩聽的。
    """
    return _SPACES.sub("", unicodedata.normalize("NFKC", text)).lower()


@dataclass(frozen=True)
class CategorySpec:
    label: str  # 講給長輩聽的說法
    overture: tuple[str, ...] = ()  # 命中即納入的 Overture 分類值
    keywords: tuple[str, ...] = ()  # 命中即納入的中文店名關鍵字
    exclude: tuple[str, ...] = ()  # 命中即排除，優先於上面兩者
    # True＝就算 Overture 分類命中，仍要求店名含關鍵字才收（見 pharmacy 的理由）。
    # 預設 False：多數類別的 Overture 分類已夠可信，靠它就能收到店名不含關鍵字的
    # 合法店家（如英文招牌）；只有實測證明該分類本身不可信時才開啟。
    require_keyword: bool = False
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
            "小吃",
            "滷味",
            "臭豆腐",
            "水餃",
            "鹹酥雞",
            "鹽酥雞",
            "肉圓",
            "碗粿",
            "米糕",
            "蚵仔",
            "麵線",
            "刈包",
            "米粉",
            "擔仔",
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
        # ⚠️ require_keyword=True（Leo 核定 2026-07-28）：Overture 的 pharmacy 分類
        # 單獨不可信，實測「附近有藥局嗎」第一名查到「元大銀行中和分行」
        # （overture_category='pharmacy'，距長輩僅 106 公尺）。對正式庫同版本資料
        # 查證：taxonomy.primary='pharmacy' 且未被上面 exclude 擋下的 5,777 筆裡，
        # 1,637 筆（28.3%）店名完全沒有中文藥局關鍵字——「家新鋁門窗」「玖泰機車行」
        # 「度小月當舖」「雲林縣虎尾科技大學」都在裡面，改成非靠 Overture 分類單軌，
        # 一律要求店名含關鍵字才收。
        # 代價已量（2026-07-28）：這 1,637 筆裡僅 9 筆（0.55%）是英文招牌的真藥局
        # （店名含 "Pharmacy"，如 "Dr Ahmed Ezzat Pharmacy"、"Future Pharmacy"），
        # 其餘全是中藥行、蔘藥行、醫療器材行、診所與各種不相干行業。漏掉的真藥局
        # 佔比極低，代價可接受，故未追加英文關鍵字；日後若要補，"pharmacy"／
        # "drugstore" 是候選詞。
        require_keyword=True,
    ),
    "clinic": CategorySpec(
        label="診所",
        # ⚠️ 2026-07-27 對正式庫查證：舊值 doctor 與 medical_clinic 在新的
        # taxonomy.primary 下**都是 0 筆**，等於這一軌是死碼、13,327 筆全靠中文關鍵字。
        # 以下為新 schema 實際存在的值（dental_clinic 刻意不收——那是 dentist 這一類，
        # 且本類的 exclude 本來就擋牙醫）。
        overture=(
            "doctors_office",
            "pediatric_clinic",
            "behavioral_or_mental_health_clinic",
            "vision_or_eye_care_clinic",
            "dialysis_clinic",
        ),
        keywords=("診所", "醫療社團法人", "聯合診所"),
        exclude=(
            "牙醫",
            "牙科",
            "齒科",
            "Dental",
            "dental",
            "整形",
            "美學",
            "醫學美容",
            "醫美",
            "減重",
            "瘦身",
            "植髮",
            "微整",
            "Aesthetic",
            "動物",
            "獸醫",
            "Veterinary",
        ),
        # 不加「寵物」（2026-07-27 實測）：全台店名含「診所」且含「寵物」僅 2 家。
        # 其中「保成中醫診所」只因標榜寵物友善會被誤殺——它是合法人類中醫診所。
    ),
    "chinese_medicine": CategorySpec(
        label="中醫",
        keywords=("中醫",),
        exclude=("美學", "美容", "瘦小臉", "動物", "獸醫"),
    ),
    "dentist": CategorySpec(
        label="牙醫",
        # ⚠️ 舊值 dentist 在新 schema 下 0 筆，已更名為 dental_clinic（實際 5,620 家）。
        # 反向檢查：其中 242 家（4%）店名不含中文關鍵字，補上這個值才收得到——
        # 例如「TISS Dental Implant」「謝尚廷植牙團隊」「Dada Dental」。
        overture=("dental_clinic",),
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
        #
        # 「會館」保留（2026-07-27 實測）：命中整復關鍵字且含「會館」、不含舒壓油壓者
        # 全台 40 家，絕大多數（艾沐經絡美學會館、瑞樂思芳香經絡會館等）正是要擋的
        # 美容 SPA 足體按摩。審查員提議移除，但用真資料查過「永和國術會館」不存在。
        # ⚠️ 補「美學」「紓壓」（Leo 核定 2026-07-28）：clinic／chinese_medicine 兩類
        # 早就有「美學」擋醫美招牌，這一類漏了。實測 72/2,607 家（2.8%）帶美容 SPA
        # 招牌，例如「Annie House經絡美學SPA工作室」「紓心經絡美學/spa精油按摩」
        # 「月澄肌境 Spa｜…｜私密處保養」；「紓壓」是「舒壓」的常見異體寫法，實測
        # 3 筆漏網。這一類的性質是寧可少推幾家、不可推錯，故從寬排除。
        label_note="長輩問「附近哪裡可以按摩」時用這一類",
        keywords=("整復", "整骨", "國術館", "推拿", "經絡", "筋絡", "傷科"),
        exclude=(
            "舒壓",
            "紓壓",
            "油壓",
            "指壓",
            "美容",
            "美學",
            "美顏",
            "美體",
            "美睫",
            "除毛",
            "寵物",
            "做臉",
            "美甲",
            "會館",
            "護膚",
            "半套",
            "全套",
            "茶室",
            "阿公店",
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
        # ⚠️ 「全家」不可單獨當關鍵字（2026-07-27 灌入後實查）：它是台灣很常見的店名開頭，
        # 實際撈到「全家旅店」（旅館）與「全家眼鏡公司-中和店」（眼鏡行）。長輩問
        # 「附近有超商嗎」被回一家旅館。改用全名，並補排除詞擋住其餘同名行業。
        keywords=("7-ELEVEN", "7-11", "統一超商", "全家便利商店", "萊爾富", "OK超商", "OK MART"),
        exclude=("旅店", "眼鏡", "旅館", "民宿", "診所", "餐廳", "牙醫"),
    ),
    "temple": CategorySpec(
        label="廟",
        # ⚠️ 舊的三個值（temple／buddhist_temple／taoist_temple）在新 schema 下全是 0 筆。
        # 反向檢查：宗教類分類命中 19,846 家，其中 8,371 家（42%）店名不含我們的關鍵字
        # 而被靜默漏掉——「濟緣堂」「茄萣明悟堂」「大湖擇善佛堂」「唯心聖教湖內道場」。
        #
        # ⚠️ **只收佛教那一個值，不可把所有 *_worship 都加進來**：新 schema 裡最大宗是
        # christian_place_of_worship（14,898 家），那是教會不是廟。長輩問「附近有廟可以
        # 拜嗎」被回一堆教會，是答非所問。教會屬另一個類別（本輪未開放）。
        # ⚠️ 已知未解的誤配（2026-07-28 審查發現，本輪不做）：983 筆 temple 的
        # overture_category 其實是各種 *_restaurant（例如「勝博殿」是日式豬排連鎖，
        # 命中單字關鍵字「殿」）。這類需要新機制（例如把 *_restaurant 直接排除在
        # overture 命中之外）才能解，留給下一個人接手。
        overture=("buddhist_place_of_worship",),
        keywords=("宮", "寺", "廟", "壇", "殿"),
        # exclude 沿用 2026-07-27 稍早的實測結果：單字關鍵字全台命中 29,501 筆，其中
        # 飯店 13、酒店 6、婚紗 4、百貨 9、餐廳 34、小吃 46、美食 41 家係誤配，真例如
        # 「漢宮大飯店」「白宮大飯店」。這條是 overture_category 不吻合時的關鍵字後援，
        # 與本次校準 overture 值無關，仍然需要防——任務書草稿曾把這裡簡化回只留
        # ("廟口",)，那是舊草稿沒跟上這道排除詞的既有修正，本檔刻意不採用。
        # 「咖啡」有實測依據（2026-07-28）：全表店名同時含（宮/寺/廟/壇/殿）與「咖啡」
        # 共 31 筆，全是咖啡店，如「Cama現烘咖啡專門店 台北行天宮店」「北港武德宮樂咖啡」。
        # 「花壇」（2026-07-28 新增）：單字關鍵字「壇」會把彰化縣花壇鄉整個地名收進來，
        # 實測 251 筆含「花壇」，例如「CJ E-bike 電動車 花壇店」「三媽臭臭鍋花壇店」
        # 「SeSA洗衣吧-花壇成功店」——這些店名剛好含「壇」字純屬地名巧合，與宗教場所無關。
        exclude=(
            "廟口",
            "飯店",
            "酒店",
            "婚紗",
            "百貨",
            "餐廳",
            "小吃",
            "美食",
            "咖啡",
            "花壇",
        ),
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
    normalized = _normalized(name)
    if any(_normalized(bad) in normalized for bad in spec.exclude):
        return False
    if overture_category and overture_category in spec.overture and not spec.require_keyword:
        return True
    return any(_normalized(good) in normalized for good in spec.keywords)
