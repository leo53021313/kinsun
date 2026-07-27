"""附近地點搜尋工具（spec 2026-07-27-附近地點搜尋）。

**繼排程工具之後第二組拿 `ToolInvocationContext` 的工具。** 座標的三條界線：

1. `elder_id` 一律從 context 取，**絕不接受模型傳入**。此路由
   `2026-07-17-長輩目前地點-design.md` 封死並寫明理由：模型會幻覺、也可能被長輩的
   話術帶偏，結果是查到別位長輩的位置——跨帳號資料外洩。
2. 座標由本工具自己去 `LocationStore` 取，不經模型的手。天氣工具走的是另一條路
   （座標寫進提示詞、模型當參數傳回來），那條路的已知風險是模型自己編座標——
   `weather._is_from_elder()` 正是為此存在。本工具直接繞開：模型沒有機會提供座標。
3. 位置不存在或過期就開口問，不猜、不用預設城市。
"""

from __future__ import annotations

from collections.abc import Callable

from kinsun.llm import ToolSpec
from kinsun.locations.store import LocationStore
from kinsun.places.categories import CATEGORIES, category_names
from kinsun.places.geo import distance_meters
from kinsun.places.refine import refine
from kinsun.places.store import PlaceStore
from kinsun.tools.registry import ToolInvocationContext

# 搜尋半徑。長輩座標在手機端已模糊到 0.01 度（約 1.1 公里），300 點蒙地卡羅實測
# 顯示 1,200 公尺可找回真實 800 公尺內店家的 97%、1,600 公尺可找回 100%。
#
# ⚠️ 查無結果時**不放大半徑**。2026-07-27 實測：以 3,000 公尺搜尋「小高拉麵」會撈到
# 板橋分店（距長輩 2,941 公尺）。系統會用完全正確的店名，把行動不便的長輩指到
# 2.9 公里外——從對話紀錄看一切正常，實際上比誠實說「查不到」傷害更大。
_RADIUS_METERS = 1500.0

# 回幾家。長輩用聽的，講超過三家他記不住；多給只是讓模型有更多機會挑錯。
_MAX_RESULTS = 5

# `place` 解析出來的中心點，離長輩已知位置最遠可以到多遠（2026-07-28 端到端實測）。
#
# ⚠️ 這道護欄防的是「模型把**店名**當地名傳進來」。實測 Nominatim 對店名照單全收：
# 「小高拉麵」→ 離長輩 3.7 公里、「一蘭拉麵」→ 7.9 公里、**「麥當勞」→ 台南，254 公里**。
# 沒有這道護欄，長輩說「我想吃麥當勞」就可能收到一串台南的店，而句子裡寫著「附近」。
# 這比原本設計時防的「板橋分店 2.9 公里」嚴重一個數量級。
#
# 取 50 公里而不是更小：長輩問「西門町附近有什麼吃的」是**合法**用法（實測離中和
# 4.9 公里），同一個縣市生活圈內的地名都該放行。50 公里約當跨縣市，那已經不是
# 「等下要去吃飯」的距離。
#
# ⚠️ 長輩位置不明或已過期時這道護欄失效（沒有基準點可比）。此時只剩「回傳字串講出
# 中心點」那道防線——所以那一道不可省。
_MAX_PLACE_METERS = 50_000.0

_NO_ELDER = "（目前不知道是誰在講話，沒辦法查他附近有什麼）"
_NO_LOCATION = "（不知道長輩現在在哪裡。請開口問他人在哪附近，不要自己猜。）"
# ⚠️ 這一句是功能本體不是文案：Overture 的 operating_status 實測 923,241/923,297 為
# NULL，我們無法排除已歇業的店。長輩走 500 公尺撲空，對陪伴型產品的信任傷害比
# 查不到更大——必須讓模型知道，它才講得出「要不要先打個電話問問」。
_UNKNOWN_HOURS = "（不確定這些店現在有沒有開，可以建議長輩先打電話問。）"
_BAD_CATEGORY = "（沒有這一類可以查。請從工具說明列出的類別裡挑一個，不要自己造。）"
_PLACE_TOO_FAR = (
    "（「{place}」離長輩太遠了，那不像是他現在講的地方——可能是把店名當地名了。"
    "請問清楚他要找哪一帶，不要直接報那邊的店。）"
)

NEARBY_SPEC = ToolSpec(
    name="search_nearby_places",
    description=(
        "查長輩住家附近有什麼店家或場所。長輩問「附近有什麼餐廳」「附近哪裡有藥局」"
        "「附近哪裡可以按摩」這類問題時用，回傳店名與距離。"
        "系統會自動用長輩手機回報的位置，不必也不可以傳他的身分。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": category_names(),
                "description": "要找哪一類。長輩問按摩、推拿、筋骨痠痛時用 chiropractic",
            },
            "place": {
                "type": "string",
                "description": (
                    "以哪裡為中心。**只填地名**（例：西門町、台北車站、淡水），"
                    "絕對不要填店名——填店名會查到那家店所在的別區，甚至別的縣市。"
                    "長輩問「我家附近」或沒特別講就不要填，系統會用他手機回報的位置。"
                    "他指名要找某一家店時也不要填，直接用 category 查那一類就好。"
                ),
            },
        },
        "required": ["category"],
    },
)


def _format(found: list, category: str, center_label: str) -> str:
    """`center_label` 是查詢中心點的地名；空字串＝以長輩自己的位置為中心。

    ⚠️ 中心點不是長輩所在地時，字串必須講出來（2026-07-28 端到端實測）。原本無論
    中心點在哪都寫死「附近的餐廳：」，於是模型把 3.7 公里外那一帶的店講成「附近」，
    而它沒有任何線索知道該改口——工具沒告訴它中心點被換過。
    """
    label = CATEGORIES[category].label
    where = f"{center_label}附近" if center_label else "附近"
    rows = []
    for item in found:
        row = f"{item.name}（走路約 {item.distance_meters} 公尺）"
        if item.phone:
            row += f"，電話 {item.phone}"
        rows.append(row)
    if not rows:
        return f"{where}查不到{label}。"
    return f"{where}的{label}：" + "；".join(rows) + "。" + _UNKNOWN_HOURS


def build_nearby_handler(
    places: PlaceStore,
    locations: LocationStore,
    *,
    clock: Callable[[], float],
    stale_after_hours: int,
    resolve_place: Callable[[str], tuple[float, float] | None],
) -> Callable[[dict, ToolInvocationContext | None], str]:
    stale_after_seconds = stale_after_hours * 3600

    def handler(args: dict, context: ToolInvocationContext | None = None) -> str:
        # 界線 1：elder_id 只認 context。args 裡若有 elder_id 一律無視（不報錯，
        # 因為報錯只會讓模型再試一次；靜靜忽略即可）。
        elder_id = context.elder_id if context else ""
        if not elder_id:
            return _NO_ELDER

        category = (args.get("category") or "").strip()
        if category not in CATEGORIES:
            # 不回顯模型傳來的字串：工具回傳會整段進模型 context，最壞的情況是
            # 金孫照著唸給長輩聽（registry.py 對例外訊息也是同一個理由只回類型名）。
            return _BAD_CATEGORY

        # 長輩位置先取出來：它同時是預設的中心點，也是 `place` 那道距離護欄的基準。
        # ⚠️ 過期的位置比沒有位置更糟——與其很有自信地報錯一個城市的店家，不如照舊
        # 開口問。門檻與 LocationFacts 共用同一個設定（LOCATION_STALE_AFTER_HOURS），
        # 兩處各有一套會在調整時漏掉其中一邊。
        location = locations.get_for_elder(elder_id)
        has_fix = (
            location is not None
            and location.latitude is not None
            and location.longitude is not None
            and clock() - location.recorded_at <= stale_after_seconds
        )

        # 界線 3：模型只能指定「地名」，不能指定座標。地名是可被地理編碼驗證的，
        # 幻覺出來的座標無法驗證。沒填就用長輩自己的位置。
        asked_place = (args.get("place") or "").strip()
        if asked_place:
            resolved = resolve_place(asked_place)
            if resolved is None:
                return f"（查不到「{asked_place}」這個地方，請問長輩是指哪裡。）"
            center_lat, center_lon = resolved
            # 距離護欄：模型很容易把店名當地名傳進來，而地理編碼會照單全收
            # （實測「麥當勞」→ 台南，離中和 254 公里）。理由詳見 _MAX_PLACE_METERS。
            if (
                has_fix
                and distance_meters(location.latitude, location.longitude, center_lat, center_lon)
                > _MAX_PLACE_METERS
            ):
                return _PLACE_TOO_FAR.format(place=asked_place)
            center_label = asked_place
        else:
            # 界線 2：座標自己去取，取不到就開口問。
            if not has_fix:
                return _NO_LOCATION
            center_lat, center_lon = location.latitude, location.longitude
            center_label = ""

        found = places.list_near(
            latitude=center_lat,
            longitude=center_lon,
            category=category,
            radius_meters=_RADIUS_METERS,
        )
        fingerprint = places.list_postcodes_near(
            latitude=center_lat,
            longitude=center_lon,
            radius_meters=_RADIUS_METERS,
        )
        # 三道處理走單一入口，順序與截斷都關在 refine() 裡（見該函式 docstring）。
        return _format(refine(found, fingerprint, limit=_MAX_RESULTS), category, center_label)

    return handler
