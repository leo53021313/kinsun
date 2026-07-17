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
