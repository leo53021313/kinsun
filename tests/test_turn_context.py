"""長輩這輪原話的傳遞：讓工具能分辨「長輩說的地點」與「模型自己猜的」。

⚠️ 這是實測逼出來的：模型不知道地點時會猜「台北市」去呼叫天氣工具，工具照查
照回，金孫就很有自信地把台北的天氣報給高雄的長輩。提示詞兩處都寫「不要自行
假設台北」，它照做不誤（實測 4/7）。

而且實測還揭穿：舊版「會開口問」根本不是模型守規矩——它一直在猜，只是猜的
字串（如「目前所在地」「您現在在哪個縣市呢？」）查不到，工具失敗後它才去問。
那條防線是意外的。故根治必須是結構性的：讓工具拒絕沒有依據的地點。
"""

from kinsun.turn_context import current_utterance, elder_utterance


def test_default_is_empty():
    assert current_utterance() == ""


def test_reads_back_inside_scope():
    with elder_utterance("我在台南，今天天氣如何？"):
        assert current_utterance() == "我在台南，今天天氣如何？"


def test_resets_after_scope():
    with elder_utterance("我在台南"):
        pass
    assert current_utterance() == ""


def test_nested_scopes_restore_outer():
    with elder_utterance("外層"):
        with elder_utterance("內層"):
            assert current_utterance() == "內層"
        assert current_utterance() == "外層"


# --- 本輪來源登記簿（2026-07-26 實測 S4：出站冒名防線的事實來源）---


def test_record_source_is_a_noop_without_a_ledger():
    """沒開帳本時完全 no-op：排程端與既有工具測試一字都不必改。"""
    from kinsun.turn_context import record_source

    record_source("hpa.gov.tw")  # 不該拋


def test_the_ledger_collects_what_tools_register():
    from kinsun.turn_context import record_source, turn_sources

    with turn_sources() as sources:
        record_source("hpa.gov.tw")
        record_source("tfc-taiwan.org.tw")
        assert sources == ["hpa.gov.tw", "tfc-taiwan.org.tw"]


def test_an_empty_name_is_not_recorded():
    """publisher 可能是空字串（爬蟲沒抓到），空的不算來源。"""
    from kinsun.turn_context import record_source, turn_sources

    with turn_sources() as sources:
        record_source("")
        assert sources == []


def test_the_ledger_is_reset_between_turns():
    """上一輪查到的來源不可以讓下一輪的冒名回覆過關。"""
    from kinsun.turn_context import record_source, turn_sources

    with turn_sources() as first:
        record_source("hpa.gov.tw")
        assert first
    with turn_sources() as second:
        assert second == []
