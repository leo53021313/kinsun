from kinsun.episodic.store import SqliteVectorStore, _cosine


def test_cosine_identical_is_one():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_orthogonal_is_zero():
    assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_zero_vector_is_zero():
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_search_orders_by_similarity():
    store = SqliteVectorStore(":memory:")
    store.add("u1", "想念孫子", [1.0, 0.0])
    store.add("u1", "今天天氣", [0.0, 1.0])
    assert store.search("u1", [0.9, 0.1], k=1) == ["想念孫子"]


def test_search_top_k_limit():
    store = SqliteVectorStore(":memory:")
    store.add("u1", "a", [1.0, 0.0])
    store.add("u1", "b", [0.9, 0.1])
    store.add("u1", "c", [0.0, 1.0])
    assert len(store.search("u1", [1.0, 0.0], k=2)) == 2


def test_dedupe_and_session_isolation():
    store = SqliteVectorStore(":memory:")
    store.add("u1", "x", [1.0, 0.0])
    store.add("u1", "x", [1.0, 0.0])
    store.add("u2", "y", [1.0, 0.0])
    assert store.search("u1", [1.0, 0.0], k=10) == ["x"]


def test_search_empty():
    assert SqliteVectorStore(":memory:").search("nobody", [1.0, 0.0], k=3) == []
