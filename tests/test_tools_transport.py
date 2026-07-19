"""交通工具（transport.py）單元測試：以 FakeTransport 模擬 TDX／OSRM／Nominatim。"""

from __future__ import annotations

import json

from kinsun.tools.transport import (
    BUS_ARRIVAL_SPEC,
    MRT_LINE_SPEC,
    PARKING_SPEC,
    ROUTE_SPEC,
    build_bus_arrival_handler,
    build_mrt_line_handler,
    build_parking_handler,
    build_route_handler,
)
from kinsun.transport import FakeTransport, Response, TransportError


def _json_response(payload: object) -> Response:
    return Response(200, {}, json.dumps(payload).encode())


# ── 工具規格 ────────────────────────────────────────────────────────────


def test_specs_have_expected_names():
    assert ROUTE_SPEC.name == "get_route"
    assert BUS_ARRIVAL_SPEC.name == "get_bus_arrival"
    assert MRT_LINE_SPEC.name == "get_mrt_line"
    assert PARKING_SPEC.name == "get_parking"


# ── 路線規劃 get_route（Nominatim + OSRM，免金鑰）─────────────────────────


def _route_transport() -> FakeTransport:
    def handler(method, url, data):
        if "nominatim" in url:
            return _json_response([{"lat": "25.0478", "lon": "121.5170"}])
        if "router.project-osrm.org" in url:
            return _json_response(
                {"code": "Ok", "routes": [{"distance": 5200.0, "duration": 900.0}]}
            )
        return _json_response({})

    return FakeTransport(handler=handler)


def test_route_returns_distance_and_time():
    handler = build_route_handler(transport=_route_transport())
    reply = handler({"origin": "台北車站", "destination": "台北101"})
    assert "5.2 公里" in reply
    assert "15 分鐘" in reply


def test_route_missing_destination_asks():
    handler = build_route_handler(transport=_route_transport())
    reply = handler({"origin": "台北車站"})
    assert "目的地" in reply


def test_route_missing_origin_asks():
    handler = build_route_handler(transport=_route_transport())
    reply = handler({"destination": "台北101"})
    assert "出發" in reply or "起點" in reply


def test_route_geocode_not_found():
    def handler_fn(method, url, data):
        return _json_response([])  # Nominatim 查不到

    handler = build_route_handler(transport=FakeTransport(handler=handler_fn))
    reply = handler({"origin": "不存在的地方", "destination": "另一個不存在"})
    assert "查不到" in reply


def test_route_transport_error_is_friendly():
    fake = FakeTransport()
    fake.error = TransportError("boom")
    handler = build_route_handler(transport=fake)
    reply = handler({"origin": "台北車站", "destination": "台北101"})
    assert "查詢" in reply and "boom" not in reply


# ── 公車到站 get_bus_arrival（TDX）───────────────────────────────────────


def _tdx_transport(query_payload: object) -> FakeTransport:
    def handler(method, url, data):
        if "openid-connect/token" in url:
            return _json_response({"access_token": "fake-token"})
        return _json_response(query_payload)

    return FakeTransport(handler=handler)


def test_bus_arrival_returns_eta():
    payload = [
        {"StopName": {"Zh_tw": "台北車站"}, "EstimatedTime": 300},
        {"StopName": {"Zh_tw": "中山"}, "EstimatedTime": None},
    ]
    handler = build_bus_arrival_handler("cid", "secret", transport=_tdx_transport(payload))
    reply = handler({"route_name": "307"})
    assert "307" in reply
    assert "台北車站" in reply


def test_bus_arrival_missing_route_asks():
    handler = build_bus_arrival_handler("cid", "secret", transport=_tdx_transport([]))
    reply = handler({})
    assert "公車" in reply or "路線" in reply


def test_bus_arrival_transport_error_is_friendly():
    fake = FakeTransport()
    fake.error = TransportError("boom")
    handler = build_bus_arrival_handler("cid", "secret", transport=fake)
    reply = handler({"route_name": "307"})
    assert "boom" not in reply
    assert "查詢" in reply or "失敗" in reply


# ── 捷運路線 get_mrt_line（TDX）──────────────────────────────────────────


def test_mrt_line_returns_line():
    payload = [
        {
            "RouteName": {"Zh_tw": "淡水信義線"},
            "Stations": [
                {"StationName": {"Zh_tw": "中山"}},
                {"StationName": {"Zh_tw": "台北車站"}},
            ],
        }
    ]
    handler = build_mrt_line_handler("cid", "secret", transport=_tdx_transport(payload))
    reply = handler({"station_name": "中山"})
    assert "淡水信義線" in reply


def test_mrt_line_not_found():
    handler = build_mrt_line_handler("cid", "secret", transport=_tdx_transport([]))
    reply = handler({"station_name": "不存在站"})
    assert "找不到" in reply


def test_mrt_line_missing_station_asks():
    handler = build_mrt_line_handler("cid", "secret", transport=_tdx_transport([]))
    reply = handler({})
    assert "站" in reply


# ── 路邊停車 get_parking（TDX）───────────────────────────────────────────


def test_parking_returns_availability():
    payload = {
        "CurbParkingSegmentAvailabilities": [
            {"ParkingSegmentName": {"Zh_tw": "忠孝東路"}, "TotalSpaces": 20, "AvailableSpaces": 5},
            {"ParkingSegmentName": {"Zh_tw": "仁愛路"}, "TotalSpaces": 10, "AvailableSpaces": 0},
        ]
    }
    handler = build_parking_handler("cid", "secret", transport=_tdx_transport(payload))
    reply = handler({"city": "taipei"})
    assert "忠孝東路" in reply
    assert "5" in reply


def test_parking_transport_error_is_friendly():
    fake = FakeTransport()
    fake.error = TransportError("boom")
    handler = build_parking_handler("cid", "secret", transport=fake)
    reply = handler({"city": "taipei"})
    assert "boom" not in reply
    assert "查詢" in reply or "失敗" in reply
