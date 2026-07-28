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


# --- 一輪的總時間預算（辛-21）---


def test_no_budget_means_no_limit():
    """沒開預算＝不限制：排程端與既有呼叫端一字不必改，行為與加這個功能之前相同。"""
    from kinsun.turn_context import remaining_budget

    assert remaining_budget() is None


def test_budget_counts_down_as_the_turn_burns_time(monkeypatch):
    """剩餘＝總預算減去已經花掉的。用 monotonic 而非 wall clock：校時不可影響一輪的預算。"""
    import kinsun.turn_context as tc

    clock = [1000.0]
    monkeypatch.setattr(tc.time, "monotonic", lambda: clock[0])

    with tc.turn_budget(30.0):
        assert tc.remaining_budget() == 30.0
        clock[0] += 25.0
        assert tc.remaining_budget() == 5.0


def test_budget_goes_negative_rather_than_clamping(monkeypatch):
    """超支要看得出來是超支：夾在 0 會讓「剛好用完」與「超支 60 秒」長得一樣。"""
    import kinsun.turn_context as tc

    clock = [1000.0]
    monkeypatch.setattr(tc.time, "monotonic", lambda: clock[0])

    with tc.turn_budget(30.0):
        clock[0] += 90.0
        assert tc.remaining_budget() == -60.0


def test_budget_is_reset_between_turns(monkeypatch):
    """上一輪燒光預算，不可以讓下一輪一開口就被判出局。"""
    import kinsun.turn_context as tc

    clock = [1000.0]
    monkeypatch.setattr(tc.time, "monotonic", lambda: clock[0])

    with tc.turn_budget(30.0):
        clock[0] += 40.0
        assert tc.remaining_budget() < 0
    with tc.turn_budget(30.0):
        assert tc.remaining_budget() == 30.0
    assert tc.remaining_budget() is None
