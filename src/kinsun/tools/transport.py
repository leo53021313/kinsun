"""交通工具：路線規劃（OSRM）、公車到站／捷運路線／路邊停車（TDX）。

路線走免金鑰的 Nominatim 地理編碼 ＋ OSRM 路線；TDX 三工具需 client 憑證，
未設定時由 composition 略過註冊（優雅降級）。HTTP 一律走共用傳輸層
（`kinsun.transport`），transport 可注入以利測試。

改寫自 Kevin 的 transport_agent 原型：抽出 4 個資料查詢函式，套上金孫的
ToolSpec／傳輸層／錯誤處理慣例；原型自帶的 Flask server、Gemini 編排與
map.html 前端不需要（CareAgent 本身即 LLM 編排器）。
"""

from __future__ import annotations

import urllib.parse
from collections.abc import Callable

from kinsun.llm import ToolSpec
from kinsun.transport import (
    HttpxTransport,
    Transport,
    TransportError,
    get_json,
    read_json,
)

_TIMEOUT = 10.0
_USER_AGENT = "KinSun/1.0 (elder-care assistant)"

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1"
_OSRM_URL = (
    "http://router.project-osrm.org/route/v1/driving/{olon},{olat};{dlon},{dlat}?overview=false"
)
_TDX_TOKEN_URL = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
_TDX_BUS_URL = (
    "https://tdx.transportdata.tw/api/basic/v2/Bus/EstimatedTimeOfArrival/"
    "City/{city}/{route}?%24top=20&%24format=JSON"
)
_TDX_MRT_URL = (
    "https://tdx.transportdata.tw/api/basic/v2/Rail/Metro/StationOfRoute/TRTC?%24format=JSON"
)
_TDX_PARKING_URL = (
    "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/"
    "ParkingSegmentAvailability/City/{city}?%24top=20&%24format=JSON"
)

# 城市口語 → TDX 城市代碼；未知一律回台北（服務範圍限台北都會區）。
_CITY_CODES = {
    "taipei": "Taipei",
    "台北": "Taipei",
    "台北市": "Taipei",
    "臺北市": "Taipei",
    "newtaipei": "NewTaipei",
    "new taipei": "NewTaipei",
    "新北": "NewTaipei",
    "新北市": "NewTaipei",
}


ROUTE_SPEC = ToolSpec(
    name="get_route",
    description=(
        "查兩地之間的開車距離與時間。長輩問「怎麼去某地、多遠、要開多久」時用。"
        "destination 必填；origin 用長輩目前位置或他說的出發地——情境附有位置就帶上，"
        "兩者都沒有就先開口問，不要自行假設。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "destination": {"type": "string", "description": "目的地名稱，例：台北榮總"},
            "origin": {"type": "string", "description": "出發地名稱；可用長輩目前位置"},
        },
        "required": ["destination"],
    },
)

BUS_ARRIVAL_SPEC = ToolSpec(
    name="get_bus_arrival",
    description="查台北／新北公車路線的即時到站時間。長輩問某號公車還多久到站時用。",
    parameters={
        "type": "object",
        "properties": {
            "route_name": {"type": "string", "description": "公車路線號，例：307、藍7"},
            "city": {"type": "string", "description": "taipei 或 newtaipei，預設 taipei"},
        },
        "required": ["route_name"],
    },
)

MRT_LINE_SPEC = ToolSpec(
    name="get_mrt_line",
    description="查台北捷運站屬於哪條路線。長輩問某捷運站在哪條線時用。",
    parameters={
        "type": "object",
        "properties": {
            "station_name": {"type": "string", "description": "捷運站名，例：中山、市政府"},
        },
        "required": ["station_name"],
    },
)

PARKING_SPEC = ToolSpec(
    name="get_parking",
    description="查台北／新北路邊停車的即時空位（前幾筆）。長輩或家屬問哪裡有停車位時用。",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "taipei 或 newtaipei，預設 taipei"},
        },
    },
)


def _city_code(city: str | None) -> str:
    return _CITY_CODES.get((city or "taipei").strip().lower(), "Taipei")


def geocode(http: Transport, place: str) -> tuple[float, float] | None:
    """地名 → (lat, lon)；查不到回 None。加 countryCode 意義的「台灣」後綴避免命中海外同名。

    公開函式（spec 2026-07-27-附近地點搜尋跨模組沿用）：`tools/places.py` 的
    `resolve_place` 借道本函式做「地名 → 座標」，不另接地理編碼服務。
    """
    url = _NOMINATIM_URL.format(q=urllib.parse.quote(f"{place} 台灣"))
    data = get_json(http, url, timeout=_TIMEOUT, headers={"User-Agent": _USER_AGENT})
    if not data:
        return None
    first = data[0]
    return float(first["lat"]), float(first["lon"])


def _tdx_token(http: Transport, client_id: str, client_secret: str) -> str:
    """向 TDX 換 access token（client_credentials）。失敗或無 token 一律 TransportError。"""
    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
    ).encode()
    response = http.request(
        "POST",
        _TDX_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT,
    )
    token = read_json(response).get("access_token", "")
    if not token:
        raise TransportError("TDX 未回傳 access_token")
    return token


def _tdx_get(http: Transport, url: str, token: str) -> object:
    return get_json(
        http,
        url,
        timeout=_TIMEOUT,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )


def build_route_handler(transport: Transport | None = None) -> Callable[[dict], str]:
    http = transport or HttpxTransport()

    def handler(args: dict) -> str:
        destination = (args.get("destination") or "").strip()
        origin = (args.get("origin") or "").strip()
        if not destination:
            return "請問長輩要去哪裡（目的地）？"
        if not origin:
            return "請問要從哪裡出發？（可用長輩目前的位置當起點）"
        try:
            origin_coords = geocode(http, origin)
            dest_coords = geocode(http, destination)
            if origin_coords is None or dest_coords is None:
                missing = origin if origin_coords is None else destination
                return f"查不到「{missing}」這個地點。"
            url = _OSRM_URL.format(
                olon=origin_coords[1],
                olat=origin_coords[0],
                dlon=dest_coords[1],
                dlat=dest_coords[0],
            )
            route = get_json(http, url, timeout=_TIMEOUT)
        except TransportError:
            return "（路線查詢暫時失敗，請稍後再試）"
        routes = route.get("routes") if isinstance(route, dict) else None
        if route.get("code") != "Ok" or not routes:
            return "（找不到這兩地之間的開車路線）"
        first = routes[0]
        km = round(first["distance"] / 1000, 1)
        minutes = round(first["duration"] / 60)
        return f"從{origin}到{destination}，約 {km} 公里，開車約 {minutes} 分鐘。"

    return handler


def build_bus_arrival_handler(
    client_id: str, client_secret: str, transport: Transport | None = None
) -> Callable[[dict], str]:
    http = transport or HttpxTransport()

    def handler(args: dict) -> str:
        route_name = (args.get("route_name") or "").strip()
        if not route_name:
            return "請問長輩要查哪一路公車？"
        city = _city_code(args.get("city"))
        try:
            token = _tdx_token(http, client_id, client_secret)
            url = _TDX_BUS_URL.format(city=city, route=urllib.parse.quote(route_name))
            data = _tdx_get(http, url, token)
        except TransportError:
            return "（公車到站查詢暫時失敗，請稍後再試）"
        stops = []
        for item in (data or [])[:5]:
            name = item.get("StopName", {}).get("Zh_tw", "未知")
            eta = item.get("EstimatedTime")
            eta_text = "即將到站或無班次資料" if eta is None else f"約 {round(eta / 60)} 分鐘後"
            stops.append(f"{name} {eta_text}")
        if not stops:
            return f"查不到 {route_name} 公車的即時到站資料。"
        return f"{route_name} 公車到站：" + "；".join(stops)

    return handler


def build_mrt_line_handler(
    client_id: str, client_secret: str, transport: Transport | None = None
) -> Callable[[dict], str]:
    http = transport or HttpxTransport()

    def handler(args: dict) -> str:
        station_name = (args.get("station_name") or "").strip()
        if not station_name:
            return "請問長輩要查哪一個捷運站？"
        try:
            token = _tdx_token(http, client_id, client_secret)
            data = _tdx_get(http, _TDX_MRT_URL, token)
        except TransportError:
            return "（捷運查詢暫時失敗，請稍後再試）"
        for route in data or []:
            stations = route.get("Stations", [])
            if any(
                station_name in station.get("StationName", {}).get("Zh_tw", "")
                for station in stations
            ):
                line = route.get("RouteName", {}).get("Zh_tw", "未知路線")
                return f"{station_name} 捷運站在{line}。"
        return f"找不到「{station_name}」的捷運路線資訊。"

    return handler


def build_parking_handler(
    client_id: str, client_secret: str, transport: Transport | None = None
) -> Callable[[dict], str]:
    http = transport or HttpxTransport()

    def handler(args: dict) -> str:
        city = _city_code(args.get("city"))
        try:
            token = _tdx_token(http, client_id, client_secret)
            url = _TDX_PARKING_URL.format(city=city)
            data = _tdx_get(http, url, token)
        except TransportError:
            return "（停車查詢暫時失敗，請稍後再試）"
        items = (data or {}).get("CurbParkingSegmentAvailabilities", [])
        rows = []
        for item in items[:5]:
            name = item.get("ParkingSegmentName", {}).get("Zh_tw", "未知")
            total = item.get("TotalSpaces", "?")
            avail = item.get("AvailableSpaces", "?")
            rows.append(f"{name} 空 {avail}/{total}")
        if not rows:
            return "查不到即時的路邊停車空位資料。"
        return "路邊停車即時空位：" + "；".join(rows)

    return handler
