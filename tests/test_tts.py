from kinsun.speech.tts import TextBubbleTts, TtsResult


def test_text_bubble_returns_text_without_audio():
    result = TextBubbleTts().synthesize("阿公您好")
    assert isinstance(result, TtsResult)
    assert result.text == "阿公您好"
    assert result.audio is None
