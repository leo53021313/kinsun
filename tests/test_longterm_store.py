from kinsun.llm import Message
from kinsun.longterm.store import Mem0LongTermStore, _format_memories_for_prompt


class _FakeMem0:
    def __init__(self, search_return=None, raise_on_search=False):
        self.added = []
        self._search_return = search_return or {"results": []}
        self._raise = raise_on_search

    def add(self, messages, user_id=None, metadata=None):
        self.added.append((messages, user_id, metadata))

    def search(self, query, user_id=None, **kwargs):
        if self._raise:
            raise RuntimeError("boom")
        return self._search_return


def test_format_empty_returns_blank():
    assert _format_memories_for_prompt({"results": []}) == ""


def test_format_lists_memories_with_provenance():
    result = {"results": [{"memory": "有高血壓", "metadata": {"provenance": "self_claimed"}}]}
    out = _format_memories_for_prompt(result)
    assert "有高血壓" in out
    assert "長者自述" in out


def test_add_maps_messages_and_metadata():
    mem = _FakeMem0()
    store = Mem0LongTermStore(mem)
    store.add("sess1", [Message("user", "我叫王大明")], provenance="self_claimed")
    messages, user_id, metadata = mem.added[0]
    assert messages == [{"role": "user", "content": "我叫王大明"}]
    assert user_id == "sess1"
    assert metadata == {"provenance": "self_claimed"}


def test_search_returns_formatted_string():
    mem = _FakeMem0(search_return={"results": [{"memory": "喜歡下棋", "metadata": {}}]})
    store = Mem0LongTermStore(mem)
    assert "喜歡下棋" in store.search("興趣", "sess1")


def test_search_failsafe_returns_blank():
    store = Mem0LongTermStore(_FakeMem0(raise_on_search=True))
    assert store.search("x", "sess1") == ""
