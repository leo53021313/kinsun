from kinsun.episodic.recall import EpisodicRecaller


class FakeEmbedder:
    def embed(self, text):
        return [1.0, 0.0]


class FakeStore:
    def __init__(self, results):
        self._results = results

    def search(self, session_id, embedding, k):
        return self._results


def test_recall_formats_episodes():
    out = EpisodicRecaller(FakeEmbedder(), FakeStore(["想念孫子"])).recall("u1", "孫子")
    assert "想念孫子" in out
    assert "先前聊過" in out


def test_recall_empty_is_blank():
    assert EpisodicRecaller(FakeEmbedder(), FakeStore([])).recall("u1", "x") == ""


class BoomEmbedder:
    def embed(self, text):
        raise RuntimeError("embed down")


def test_recall_failsafe_on_error():
    assert EpisodicRecaller(BoomEmbedder(), FakeStore(["x"])).recall("u1", "x") == ""
