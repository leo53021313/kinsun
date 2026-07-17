"""Open-Meteo 天氣查詢工具（免金鑰）。HTTP 走共用傳輸層，transport 可注入以利測試。"""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable

from kinsun.llm import ToolSpec
from kinsun.transport import Transport, UrllibTransport, get_json

# ⚠️ 本描述與 agent.py 的地點三句必須語意一致。Bug 2 的根因就是兩者矛盾：工具
# 說「不知道地點就先開口問」、system prompt 說「直接用那個地點」，兩段都進模型
# 的 context，模型選了保守解，定位功能靜默失效整整一天。改一處必須檢查另一處。
WEATHER_SPEC = ToolSpec(
    name="get_weather",
    description=(
        "查詢指定地點今天的天氣（概況與氣溫）。"
        "情境若附上長輩目前位置與座標，而他問的就是所在地的天氣，帶上該座標與地名呼叫，不要多問。"
        "他問的是別的地方（例如等下要去哪裡），就用他說的地點名稱、不要帶座標。"
        "兩者都不知道時，先開口問他要查哪裡，不要自行假設台北。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "地點名稱，例：台南、高雄。永遠要帶——回覆時用它稱呼地點。",
            },
            "latitude": {
                "type": "number",
                "description": "情境附的座標；只有在長輩問的就是他所在地時才帶",
            },
            "longitude": {"type": "number", "description": "同 latitude"},
        },
        "required": ["location"],
    },
)

# ⚠️ countryCode=TW 不可拿掉：沒有它，「台南」會命中中國山西省的台南
# （35.56, 113.14），金孫會用山西的氣溫回答問台南天氣的長輩。
#
# 代價是命中率低——實測全台 22 縣市只有 6 個查得到（Open-Meteo 的台灣地名索引
# 用「臺」不用「台」、且多數縣市只收錄不帶「市／縣」字尾的形式）。刻意不做
# 多變體 fallback 去提高命中率：實測「新竹縣」會因此命中屏東的一個「新竹」村
# （22.46, 120.47），而新竹市在 24.80, 120.97——那是把「查不到」換成「查錯」，
# 與本行要修的 bug 同型。
#
# 寧可答不出來，不可答錯。定位路徑不走這條（它有座標，直接查預報）。
_GEOCODE_URL = (
    "https://geocoding-api.open-meteo.com/v1/search"
    "?name={name}&count=1&language=zh&format=json&countryCode=TW"
)
_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,weather_code&daily=temperature_2m_max,temperature_2m_min"
    "&timezone=Asia%2FTaipei&forecast_days=1"
)

_WMO = {
    0: "晴朗",
    1: "大致晴朗",
    2: "局部多雲",
    3: "陰天",
    45: "有霧",
    48: "有霧",
    51: "毛毛雨",
    53: "毛毛雨",
    55: "毛毛雨",
    61: "下雨",
    63: "下雨",
    65: "大雨",
    66: "凍雨",
    67: "凍雨",
    71: "下雪",
    73: "下雪",
    75: "大雪",
    80: "陣雨",
    81: "陣雨",
    82: "強陣雨",
    95: "雷雨",
    96: "雷雨",
    99: "雷雨夾冰雹",
}


def build_weather_handler(transport: Transport | None = None) -> Callable[[dict], str]:
    http = transport or UrllibTransport()

    def handler(args: dict) -> str:
        location = (args.get("location") or "").strip()
        if not location:
            return "請告訴我您想查哪個地方的天氣。"
        lat, lon = args.get("latitude"), args.get("longitude")
        # 兩個都有才用座標：半套＝沒有。定位路徑（手機回報）必然兩個都給，
        # 半套只可能來自模型出錯，那時走地理編碼比拿半個座標去猜安全。
        # ⚠️ 刻意不驗證座標範圍（spec 元件設計 5）：擋不了模型幻覺（後果是天氣
        # 答錯，與地理編碼失準同級），卻會擋掉出國的長輩，且驗證失敗也只能說
        # 「查不到」——沒有比現況更好。
        if lat is None or lon is None:
            geo = get_json(http, _GEOCODE_URL.format(name=urllib.parse.quote(location)), timeout=10)
            results = geo.get("results") or []
            if not results:
                return f"查不到「{location}」這個地點的天氣。"
            lat, lon = results[0]["latitude"], results[0]["longitude"]
        fc = get_json(http, _FORECAST_URL.format(lat=lat, lon=lon), timeout=10)
        current = fc.get("current") or {}
        daily = fc.get("daily") or {}
        desc = _WMO.get(current.get("weather_code"), "天氣")
        now_t = current.get("temperature_2m")
        highs = (daily.get("temperature_2m_max") or [None])[0]
        lows = (daily.get("temperature_2m_min") or [None])[0]
        parts = [f"{location}今天{desc}"]
        if lows is not None and highs is not None:
            parts.append(f"氣溫約 {round(lows)}–{round(highs)}°C")
        if now_t is not None:
            parts.append(f"目前 {round(now_t)}°C")
        return "，".join(parts) + "。"

    return handler
