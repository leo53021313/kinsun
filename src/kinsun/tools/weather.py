"""Open-Meteo 天氣查詢工具（免金鑰）。HTTP 走 stdlib urllib，fetch 可注入以利測試。"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from collections.abc import Callable

from kinsun.llm import ToolSpec

WEATHER_SPEC = ToolSpec(
    name="get_weather",
    description="查詢指定地點今天的天氣（概況與氣溫）。",
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


def _urllib_fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310 - 固定 https Open-Meteo
        return json.loads(response.read().decode("utf-8"))


def build_weather_handler(
    fetch_json: Callable[[str], dict] = _urllib_fetch_json,
) -> Callable[[dict], str]:
    def handler(args: dict) -> str:
        location = (args.get("location") or "").strip()
        if not location:
            return "請告訴我您想查哪個地方的天氣。"
        geo = fetch_json(_GEOCODE_URL.format(name=urllib.parse.quote(location)))
        results = geo.get("results") or []
        if not results:
            return f"查不到「{location}」這個地點的天氣。"
        place = results[0]
        fc = fetch_json(_FORECAST_URL.format(lat=place["latitude"], lon=place["longitude"]))
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
