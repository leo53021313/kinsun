import json

from kinsun.tools.weather import WEATHER_SPEC, build_weather_handler
from kinsun.transport import FakeTransport, Response
from kinsun.turn_context import elder_utterance

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


def _url_recorder():
    urls: list[str] = []

    def handler(method, url, data):
        urls.append(url)
        payload = _GEO if "geocoding" in url else _FC
        return Response(200, {}, json.dumps(payload).encode())

    return urls, FakeTransport(handler=handler)


def test_handler_with_coords_skips_geocoding():
    """定位路徑：有座標就直接查預報，不碰地理編碼。

    這是 Bug 3 的根治——Open-Meteo 的台灣地名索引只有 6/22 命中，而
    reverseGeocodeAsync 回的正是「台南市」這種查不到的字串。有座標就別譯了。
    """
    urls, transport = _url_recorder()

    out = build_weather_handler(transport)(
        {"location": "台南市", "latitude": 22.99, "longitude": 120.21}
    )

    assert not any("geocoding" in u for u in urls), "有座標時不該呼叫地理編碼"
    assert "22.99" in urls[0] and "120.21" in urls[0]
    assert "台南市" in out  # 地名仍用於稱呼


def test_handler_without_coords_uses_geocoding():
    """長輩口說地名的路徑：沒有座標才譯。"""
    urls, transport = _url_recorder()

    build_weather_handler(transport)({"location": "台南"})

    assert any("geocoding" in u for u in urls)


def test_handler_with_only_one_coord_uses_geocoding():
    """半套座標＝沒有座標。不猜、不半套查。"""
    urls, transport = _url_recorder()

    build_weather_handler(transport)({"location": "台南", "latitude": 22.99})

    assert any("geocoding" in u for u in urls)


def test_weather_spec_tells_model_when_to_pass_coords():
    """⚠️ Bug 2 的回歸防線：本描述與 agent.py 的地點三句必須語意一致。

    Bug 2 的根因就是兩者矛盾——工具說「不知道地點就先開口問」，system prompt
    說「直接用那個地點」。兩段都會進模型的 context，模型選了保守解，定位功能
    靜默失效整整一天。

    ⚠️ 這只是釘字串。行為驗證做不到——假 LLM 不會推理，兩段矛盾的提示詞在它
    眼裡只是兩個字串。真正的驗證見 scripts/anchoring_probe.py。
    """
    assert "他問的就是所在地的天氣，帶上該座標與地名呼叫，不要多問" in WEATHER_SPEC.description
    assert "不要帶座標" in WEATHER_SPEC.description
    assert "兩者都不知道時，先開口問" in WEATHER_SPEC.description


def test_refuses_location_the_elder_never_said():
    """⚠️ 結構性防線：沒有座標時，地名必須真的來自長輩的原話。

    實測（真 Gemini）：模型不知道長輩在哪時會猜「台北市」去呼叫，工具照查照回，
    金孫就把台北的天氣報給別處的長輩（4/7）。提示詞在兩處都寫著「不要自行假設
    台北」，它照做不誤——這不是措辭問題，是模型有能力猜。本防線拿掉它的能力。
    """
    urls, transport = _url_recorder()

    with elder_utterance("今天天氣如何？"):
        out = build_weather_handler(transport)({"location": "台北市"})

    assert not urls, "不該碰任何外部 API"
    assert "長輩沒有說" in out and "問" in out


def test_allows_location_the_elder_said():
    urls, transport = _url_recorder()

    with elder_utterance("我在台南，今天天氣如何？"):
        build_weather_handler(transport)({"location": "台南"})

    assert any("geocoding" in u for u in urls)


def test_allows_normalised_location_the_elder_said():
    """長輩說「台北」、模型正規化成「台北市」去查——那是它該做的事（地理編碼
    只認得完整市名），不可因字尾不同就誤拒。"""
    urls, transport = _url_recorder()

    with elder_utterance("我在台北，今天天氣如何？"):
        build_weather_handler(transport)({"location": "台北市"})

    assert any("geocoding" in u for u in urls)


def test_coords_bypass_the_utterance_check():
    """有座標＝手機回報的，本來就不是模型猜的，不需要出現在原話裡。"""
    urls, transport = _url_recorder()

    with elder_utterance("今天天氣如何？"):
        build_weather_handler(transport)(
            {"location": "台南市", "latitude": 22.99, "longitude": 120.21}
        )

    assert not any("geocoding" in u for u in urls)
    assert urls, "應直接查預報"


def test_no_utterance_context_allows_lookup():
    """排程端／主動關懷沒有長輩原話（contextvar 為空）：不設限，維持既有行為。

    那條路徑走 generate、根本沒有工具可用（見 agent.py），故不會有人踩到；
    但若日後有，靜默拒絕比放行更難查。
    """
    urls, transport = _url_recorder()

    build_weather_handler(transport)({"location": "台南"})

    assert any("geocoding" in u for u in urls)
