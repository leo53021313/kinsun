from kinsun.recall import MemoryContext


class _Knowledge:
    def __init__(self, text):
        self._text = text

    def recall(self, session_id):
        return self._text


class _Episodic:
    def __init__(self, text):
        self._text = text

    def recall(self, session_id, query):
        return self._text


def test_combines_knowledge_and_episodic():
    ctx = MemoryContext(_Knowledge("【事實】"), _Episodic("【情緒】"))
    assert ctx.recall("u1", "嗨") == "【事實】【情緒】"


def test_handles_blank_sources():
    ctx = MemoryContext(_Knowledge(""), _Episodic("【情緒】"))
    assert ctx.recall("u1", "嗨") == "【情緒】"
