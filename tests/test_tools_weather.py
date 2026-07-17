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


def test_geocode_request_is_limited_to_taiwan():
    """⚠️ Bug 1：地理編碼未限定國家時，「台南」會命中中國山西省的台南
    （35.56, 113.14），金孫會用山西的氣溫回答問台南天氣的長輩，語氣毫無遲疑。

    寧可答不出來，不可答錯——限定 TW 後命中率會下降（實測全台 22 縣市僅 6 個
    查得到），但錯答無法補救、查不到至少誠實。
    """
    urls: list[str] = []

    def handler(method, url, data):
        urls.append(url)
        payload = _GEO if "geocoding" in url else _FC
        return Response(200, {}, json.dumps(payload).encode())

    build_weather_handler(FakeTransport(handler=handler))({"location": "台南"})

    geocode_url = next(u for u in urls if "geocoding" in u)
    assert "countryCode=TW" in geocode_url
