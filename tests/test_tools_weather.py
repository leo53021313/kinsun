import json

from kinsun.tools.weather import WEATHER_SPEC, build_weather_handler
from kinsun.transport import FakeTransport, Response

_GEO = {"results": [{"latitude": 25.0, "longitude": 121.5, "name": "Taipei"}]}
_FC = {
    "current": {"temperature_2m": 25.3, "weather_code": 2},
    "daily": {"temperature_2m_max": [28.1], "temperature_2m_min": [22.4]},
}


def _transport(geo, fc):
    def handler(method, url, data):
        payload = geo if "geocoding" in url else fc
        return Response(200, {}, json.dumps(payload).encode())

    return FakeTransport(handler=handler)


def test_weather_spec_name():
    assert WEATHER_SPEC.name == "get_weather"


def test_handler_formats_weather():
    out = build_weather_handler(_transport(_GEO, _FC))({"location": "台北"})
    assert "台北" in out
    assert "多雲" in out
    assert "22" in out and "28" in out


def test_handler_empty_location():
    out = build_weather_handler(_transport(_GEO, _FC))({"location": "  "})
    assert "哪個地方" in out


def test_handler_location_not_found():
    out = build_weather_handler(_transport({"results": []}, _FC))({"location": "不存在地"})
    assert "查不到" in out
