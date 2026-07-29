"""長輩目前地點：Protocol、Postgres 實作與測試替身。

單一狀態表（一位長輩一列），故 `save` 為 upsert 而非 append-only 事件流水帳
（D-42 例外：`ElderLocation` 與三件套同住本檔，比照 `proactive/preferences.py`）。

⚠️ 存地名與**模糊座標**（約 0.01 度／1.1 公里，手機端四捨五入後才上傳）。原設計為
「只存地名、不存座標」，已由 `2026-07-17-天氣地點正確性-design.md` 推翻——實測顯示
地名路徑只有 6/22 縣市查得到。附近地點搜尋（spec 2026-07-27）亦依賴這兩個欄位。

刻意不提供 `list_all`：目前無任何呼叫端需要，而「一次撈出全體長輩現在在哪」正是
這份資料最不該有的介面。YAGNI 與最小權限在此同向。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kinsun.db import Database, _Errors

_COLUMNS = "elder_id, place, recorded_at, latitude, longitude"

# 地表座標的合法範圍。邊界值屬合法（±90／±180 是真的地方）。
_LAT_MAX = 90.0
_LON_MAX = 180.0


def is_valid_coordinate(latitude: object, longitude: object) -> bool:
    """這組座標是不是地表上的一個點（V-04，2026-07-29）。

    ## 為什麼住在領域層而不是各通道自己判

    有兩個呼叫端：`channels/app/ws.py` 的 JSON 訊框與 `channels/app/turns.py` 的
    query 參數。兩邊各寫一份正是 2026-07-28 位置鍵名不合那個故障的成因——兩邊的
    單元測試各自斷言自己那一版契約，所以**兩邊都是綠的**，而長輩的位置整晚沒進庫。

    ## 為什麼型別與範圍一起判

    兩者不合的後果完全相同：寫進去的是一個假位置。而假位置不只是一筆髒資料——
    `LocationFacts` 會把它注入每一輪的提示詞，附近地點搜尋會拿它當圓心，於是長輩
    問「附近有沒有藥局」，答案是北極圈的。

    ⚠️ `bool` 要單獨排除：它是 `int` 的子型別，`float(True)` 是 1.0——傳 `true`
    不報錯，會**安靜地**把長輩記在幾內亞灣外海（WS 訊框實測確認）。

    ⚠️ 判準寫成 `-90 <= lat <= 90` 而不是 `abs(lat) > 90`：`json.loads` 接受
    `NaN`／`Infinity` 字面值，而 NaN 的比較恆為 False——前者擋得住，後者漏掉。
    """
    for value, limit in ((latitude, _LAT_MAX), (longitude, _LON_MAX)):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if not -limit <= value <= limit:
            return False
    return True


# 地名長度上限（V-05，2026-07-29）。
#
# ⚠️ **刻意訂得寬**。地名被拒的失敗模式是**靜默的**——伺服器端忽略、不回錯，長輩那端
# 的表現是金孫又開始反問「您人在哪裡」，而後台查不出原因。那正是 2026-07-28 那次位置
# 故障的症狀。App 送的是 `address.city ?? subregion ?? region`（全是短的行政區名），
# 100 字遠遠夠用；這個界線是為了擋掉實測抓到的 **2 萬字地名**——它會原樣落庫，而且
# **每一輪都注入提示詞**，既燒 token 也是提示注入的入口。
MAX_PLACE_CHARS = 100


def is_valid_place(place: object) -> bool:
    """這個地名可不可以寫進庫（V-05，2026-07-29）。

    與 `is_valid_coordinate` 同住一處、同一個理由：WS 訊框與 REST query 兩個呼叫端
    共用，各寫一份會重演 2026-07-28 鍵名不合那次——兩邊測試各斷言自己那版契約，
    全綠而長輩的位置整晚沒進庫。

    空字串與純空白回 False：那是「這輪沒有位置」（未授權、室內收不到），既有語意是
    不寫入也不清空舊值，與「地名太長」走同一條分支即可。
    """
    if not isinstance(place, str):
        return False
    cleaned = place.strip()
    return bool(cleaned) and len(cleaned) <= MAX_PLACE_CHARS


@dataclass(frozen=True)
class ElderLocation:
    elder_id: str
    place: str  # 地名，如「台南市」
    # ⚠️ 我們**收到**的時刻，不是 GPS 定位的時刻；兩者落差為已知誤差來源（見 spec 已知限制 3）。
    recorded_at: float
    # 模糊座標（約 0.01 度／1.1 公里，手機端四捨五入後才上傳）。None＝我們不知道
    # 它在哪：PR #55 寫入的既有列即此情形，LocationFacts 會退回只注入地名。
    latitude: float | None = None
    longitude: float | None = None


class LocationError(Exception):
    """地點資料讀寫失敗。"""


class LocationStore(Protocol):
    def save(self, location: ElderLocation) -> None: ...
    def get_for_elder(self, elder_id: str) -> ElderLocation | None: ...


class PgLocationStore:
    def __init__(self, db: Database) -> None:
        self._db = _Errors(db, lambda m: LocationError(f"地點資料存取失敗：{m}"))

    def save(self, location: ElderLocation) -> None:
        self._db.execute(
            f"INSERT INTO elder_locations ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (elder_id) DO UPDATE SET "
            "place = EXCLUDED.place, recorded_at = EXCLUDED.recorded_at, "
            "latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude",
            (
                location.elder_id,
                location.place,
                location.recorded_at,
                location.latitude,
                location.longitude,
            ),
        )

    def get_for_elder(self, elder_id: str) -> ElderLocation | None:
        row = self._db.query_one(
            f"SELECT {_COLUMNS} FROM elder_locations WHERE elder_id = %s", (elder_id,)
        )
        return ElderLocation(*row) if row else None


class FakeLocationStore:
    """LocationStore 的記憶體替身（測試用，不碰 DB）。"""

    def __init__(self) -> None:
        self._locations: dict[str, ElderLocation] = {}

    def save(self, location: ElderLocation) -> None:
        self._locations[location.elder_id] = location

    def get_for_elder(self, elder_id: str) -> ElderLocation | None:
        return self._locations.get(elder_id)
