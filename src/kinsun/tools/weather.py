"""Open-Meteo 天氣查詢工具（免金鑰）。HTTP 走共用傳輸層，transport 可注入以利測試。"""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable

from kinsun.llm import ToolSpec
from kinsun.transport import Transport, UrllibTransport, get_json

WEATHER_SPEC = ToolSpec(
    name="get_weather",
    description=(
        "查詢指定地點今天的天氣（概況與氣溫）。"
        "只有在你已確認長輩要查哪個城市時才呼叫；"
        "若不知道地點，先開口問長輩人在哪個城市，不要自行假設台北。"
    ),
    parameters={
        "type": "object",
        "properties": {"location": {"type": "string", "description": "地點名稱，例：台北、高雄"}},
        "required": ["location"],
    },
)

_GEOCODE_URL = (
    "https://geocoding-api.open-meteo.com/v1/search?name={name}&count=1&language=zh&format=json"
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
        geo = get_json(http, _GEOCODE_URL.format(name=urllib.parse.quote(location)), timeout=10)
        results = geo.get("results") or []
        if not results:
            return f"查不到「{location}」這個地點的天氣。"
        place = results[0]
        fc = get_json(
            http,
            _FORECAST_URL.format(lat=place["latitude"], lon=place["longitude"]),
            timeout=10,
        )
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
