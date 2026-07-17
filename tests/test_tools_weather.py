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
    with elder_utterance("台北天氣如何？"):
        out = build_weather_handler(_transport(_GEO, _FC))({"location": "台北"})
    assert "台北" in out
    assert "多雲" in out
    assert "22" in out and "28" in out


def test_handler_empty_location():
    out = build_weather_handler(_transport(_GEO, _FC))({"location": "  "})
    assert "哪個地方" in out


def test_handler_location_not_found():
    with elder_utterance("不存在地的天氣？"):
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

    with elder_utterance("恆春天氣如何？"):
        build_weather_handler(FakeTransport(handler=handler))({"location": "恆春"})

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
    """長輩口說地名的路徑：沒有座標才譯（縣市名走內建座標表，故用鄉鎮名測）。"""
    urls, transport = _url_recorder()

    with elder_utterance("恆春天氣如何？"):
        build_weather_handler(transport)({"location": "恆春"})

    assert any("geocoding" in u for u in urls)


def test_handler_with_only_one_coord_uses_geocoding():
    """半套座標＝沒有座標。不猜、不半套查。"""
    urls, transport = _url_recorder()

    with elder_utterance("恆春天氣如何？"):
        build_weather_handler(transport)({"location": "恆春", "latitude": 22.99})

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

    assert urls and not any("geocoding" in u for u in urls)  # 走縣市座標表直接查預報
    assert "latitude=22.99" in urls[0]


def test_allows_normalised_location_the_elder_said():
    """長輩說「台北」、模型正規化成「台北市」去查——那是它該做的事（地理編碼
    只認得完整市名），不可因字尾不同就誤拒。"""
    urls, transport = _url_recorder()

    with elder_utterance("我在台北，今天天氣如何？"):
        build_weather_handler(transport)({"location": "台北市"})

    assert urls and not any("geocoding" in u for u in urls)  # 走縣市座標表直接查預報
    assert "latitude=25.04" in urls[0]


def test_coords_bypass_the_utterance_check():
    """有座標＝手機回報的，本來就不是模型猜的，不需要出現在原話裡。"""
    urls, transport = _url_recorder()

    with elder_utterance("今天天氣如何？"):
        build_weather_handler(transport)(
            {"location": "台南市", "latitude": 22.99, "longitude": 120.21}
        )

    assert not any("geocoding" in u for u in urls)
    assert urls, "應直接查預報"


def test_no_utterance_refuses_model_picked_location():
    """主動問候已可走工具迴圈（2026-07-17）：沒有長輩原話＝只有座標可信。

    放行的後果是問候時模型自選地名（實測慣猜台北）照查照報——跟台南阿嬤說
    台北的天氣。座標路徑（手機回報＋LocationFacts 注入）不受影響。
    """
    urls, transport = _url_recorder()

    out = build_weather_handler(transport)({"location": "台南"})

    assert not urls, "沒有原話也沒有座標：不該碰任何外部 API"
    assert "問" in out


def test_no_utterance_coords_path_still_allowed():
    """問候時情境附了新鮮定位座標：照查（座標來自手機回報，不是模型猜的）。"""
    urls, transport = _url_recorder()

    out = build_weather_handler(transport)(
        {"location": "台南市", "latitude": 22.99, "longitude": 120.21}
    )

    assert urls and not any("geocoding" in u for u in urls)
    assert "台南市" in out


# --- 縣市座標表（2026-07-17 功能測試：長輩明說「高雄」仍回「查不到」）---


def _forecast_only_transport(urls: list[str]):
    """只允許預報請求的傳輸層：走到地理編碼就代表查表沒生效。"""

    def handler(method, url, data):
        urls.append(url)
        assert "geocoding" not in url, "縣市名不應再走地理編碼"
        return Response(200, {}, json.dumps(_FC).encode())

    return FakeTransport(handler=handler)


def test_county_name_uses_builtin_coords_not_geocoding():
    urls: list[str] = []
    with elder_utterance("我等下要去高雄，那邊天氣如何？"):
        out = build_weather_handler(_forecast_only_transport(urls))({"location": "高雄"})
    assert "高雄" in out
    assert any("latitude=22.63" in u for u in urls)


def test_tai_variant_is_normalized():
    urls: list[str] = []
    with elder_utterance("臺南天氣如何？"):
        out = build_weather_handler(_forecast_only_transport(urls))({"location": "臺南市"})
    assert "臺南市" in out
    assert any("latitude=22.99" in u for u in urls)


def test_bare_ambiguous_name_defaults_to_city():
    """「新竹」不帶字尾時取新竹市（不可退回地理編碼——會命中屏東的新竹村）。"""
    urls: list[str] = []
    with elder_utterance("新竹會不會冷？"):
        build_weather_handler(_forecast_only_transport(urls))({"location": "新竹"})
    assert any("latitude=24.8" in u for u in urls)


def test_county_suffix_is_respected():
    """「新竹縣」必須用縣的座標，不可吃到新竹市。"""
    urls: list[str] = []
    with elder_utterance("新竹縣天氣？"):
        build_weather_handler(_forecast_only_transport(urls))({"location": "新竹縣"})
    assert any("latitude=24.84" in u for u in urls)


def test_non_county_place_still_geocodes():
    urls: list[str] = []

    def handler(method, url, data):
        urls.append(url)
        payload = _GEO if "geocoding" in url else _FC
        return Response(200, {}, json.dumps(payload).encode())

    with elder_utterance("恆春鎮天氣？"):
        out = build_weather_handler(FakeTransport(handler=handler))({"location": "恆春鎮"})
    assert "恆春鎮" in out
    assert any("geocoding" in u for u in urls)
