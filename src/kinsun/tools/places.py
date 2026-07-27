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

import logging
from collections.abc import Callable

from kinsun.llm import ToolSpec
from kinsun.locations.store import LocationStore
from kinsun.places.categories import CATEGORIES, category_names
from kinsun.places.refine import refine
from kinsun.places.store import PlaceStore
from kinsun.tools.registry import ToolInvocationContext

logger = logging.getLogger("kinsun.tools.places")

# 搜尋半徑。長輩座標在手機端已模糊到 0.01 度（約 1.1 公里），300 點蒙地卡羅實測
# 顯示 1,200 公尺可找回真實 800 公尺內店家的 97%、1,600 公尺可找回 100%。
#
# ⚠️ 查無結果時**不放大半徑**。2026-07-27 實測：以 3,000 公尺搜尋「小高拉麵」會撈到
# 板橋分店（距長輩 2,941 公尺）。系統會用完全正確的店名，把行動不便的長輩指到
# 2.9 公里外——從對話紀錄看一切正常，實際上比誠實說「查不到」傷害更大。
_RADIUS_METERS = 1500.0

# 回幾家。長輩用聽的，講超過三家他記不住；多給只是讓模型有更多機會挑錯。
_MAX_RESULTS = 5

_NO_ELDER = "（目前不知道是誰在講話，沒辦法查他附近有什麼）"
_NO_LOCATION = "（不知道長輩現在在哪裡。請開口問他人在哪附近，不要自己猜。）"
# ⚠️ 這一句是功能本體不是文案：Overture 的 operating_status 實測 923,241/923,297 為
# NULL，我們無法排除已歇業的店。長輩走 500 公尺撲空，對陪伴型產品的信任傷害比
# 查不到更大——必須讓模型知道，它才講得出「要不要先打個電話問問」。
_UNKNOWN_HOURS = "（不確定這些店現在有沒有開，可以建議長輩先打電話問。）"
_BAD_CATEGORY = "（沒有這一類可以查。請從工具說明列出的類別裡挑一個，不要自己造。）"

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
                    "以哪裡為中心。長輩問的是別的地方時才填（例：西門町）；"
                    "問「我家附近」或沒特別講就不要填，系統會用他手機回報的位置"
                ),
            },
        },
        "required": ["category"],
    },
)


def _format(found: list, category: str) -> str:
    label = CATEGORIES[category].label
    rows = []
    for item in found:
        row = f"{item.name}（走路約 {item.distance_meters} 公尺）"
        if item.phone:
            row += f"，電話 {item.phone}"
        rows.append(row)
    if not rows:
        return f"附近查不到{label}。"
    return f"附近的{label}：" + "；".join(rows) + "。" + _UNKNOWN_HOURS


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

        # 界線 3：模型只能指定「地名」，不能指定座標。地名是可被地理編碼驗證的，
        # 幻覺出來的座標無法驗證。沒填就用長輩自己的位置。
        asked_place = (args.get("place") or "").strip()
        if asked_place:
            resolved = resolve_place(asked_place)
            if resolved is None:
                return f"（查不到「{asked_place}」這個地方，請問長輩是指哪裡。）"
            center_lat, center_lon = resolved
        else:
            # 界線 2：座標自己去取，取不到就開口問。
            location = locations.get_for_elder(elder_id)
            if location is None or location.latitude is None or location.longitude is None:
                return _NO_LOCATION
            # ⚠️ 過期的位置比沒有位置更糟——與其很有自信地報錯一個城市的店家，不如照舊
            # 開口問。門檻與 LocationFacts 共用同一個設定（LOCATION_STALE_AFTER_HOURS），
            # 兩處各有一套會在調整時漏掉其中一邊。
            if clock() - location.recorded_at > stale_after_seconds:
                return _NO_LOCATION
            center_lat, center_lon = location.latitude, location.longitude

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
        return _format(refine(found, fingerprint, limit=_MAX_RESULTS), category)

    return handler
