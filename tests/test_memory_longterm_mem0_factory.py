from kinsun.config import load_settings
from kinsun.memory.longterm.mem0_factory import (
    _disable_telemetry,
    _instrument_tracing,
    build_mem0_config,
)
from kinsun.memory.longterm.provenance import CUSTOM_FACT_EXTRACTION_PROMPT
from kinsun.tracing import client as tracing_client
from kinsun.tracing import decorators as tracing_decorators

_ENV = {
    "LINE_CHANNEL_SECRET": "s",
    "LINE_CHANNEL_ACCESS_TOKEN": "t",
    "GEMINI_API_KEY": "k",
    "GEMINI_MODEL": "gemini-x",
    "LONGTERM_EMBEDDING_MODEL": "BAAI/bge-m3",
    "LONGTERM_EMBEDDING_BACKEND": "local",
    "LONGTERM_EMBEDDING_ENDPOINT": "http://127.0.0.1:8003/v1",
    "DATABASE_URL": "postgresql://u:p@h:5432/db",
}

_GEMINI_ENV = {
    **_ENV,
    "LONGTERM_EMBEDDING_MODEL": "models/gemini-embedding-001",
    "LONGTERM_EMBEDDING_BACKEND": "gemini",
    "LONGTERM_EMBEDDING_ENDPOINT": "",
}


def test_build_mem0_config_shape():
    cfg = build_mem0_config(load_settings(_ENV))
    assert cfg["llm"]["provider"] == "gemini"
    assert cfg["llm"]["config"]["model"] == "gemini-x"
    assert cfg["embedder"]["provider"] == "openai"
    assert cfg["embedder"]["config"]["openai_base_url"] == "http://127.0.0.1:8003/v1"
    assert cfg["vector_store"]["provider"] == "supabase"
    assert cfg["vector_store"]["config"]["connection_string"] == "postgresql://u:p@h:5432/db"
    assert "graph_store" not in cfg
    assert cfg["version"] == "v1.1"


def test_build_mem0_config_includes_custom_instructions():
    cfg = build_mem0_config(load_settings(_ENV))
    assert cfg["custom_instructions"] == CUSTOM_FACT_EXTRACTION_PROMPT


def test_build_mem0_config_sets_consistent_embedding_dims():
    """embedder 輸出維度必須與向量庫維度一致，否則向量查詢會維度不符。

    ⚠️ 維度由 backend 決定（BGE-M3 dense 1024／Gemini 768），兩邊必須同源，
    不可各自寫死——2026-08-07 換 backend 時，這兩個數字對不上就是整個長期記憶
    查不到東西，而 mem0 是靜默退化成「沒有記憶」、不會報錯。
    """
    cfg = build_mem0_config(load_settings(_ENV))
    embedder_dims = cfg["embedder"]["config"]["embedding_dims"]
    store_dims = cfg["vector_store"]["config"]["embedding_model_dims"]
    assert embedder_dims == store_dims == 1024


def test_build_mem0_config_falls_back_to_gemini_backend():
    """backend 切回 gemini 時，provider 與維度都要跟著回去（切換需重建向量表）。"""
    cfg = build_mem0_config(load_settings(_GEMINI_ENV))
    assert cfg["embedder"]["provider"] == "gemini"
    assert "openai_base_url" not in cfg["embedder"]["config"]
    embedder_dims = cfg["embedder"]["config"]["embedding_dims"]
    store_dims = cfg["vector_store"]["config"]["embedding_model_dims"]
    assert embedder_dims == store_dims == 768


def test_local_backend_requires_endpoint():
    """地端 backend 少了 endpoint 要當場拒絕，不可讓 mem0 預設去打 api.openai.com。"""
    import pytest

    from kinsun.memory.longterm.mem0_factory import build_mem0_config as build

    broken = {**_ENV, "LONGTERM_EMBEDDING_ENDPOINT": ""}
    with pytest.raises(ValueError, match="LONGTERM_EMBEDDING_ENDPOINT"):
        build(load_settings(broken))


def test_disable_telemetry_sets_env_only_if_absent():
    """關閉 mem0 遙測（隱私），但尊重使用者顯式設定。"""
    env = {}
    _disable_telemetry(env)
    assert env["MEM0_TELEMETRY"] == "False"
    explicit = {"MEM0_TELEMETRY": "True"}
    _disable_telemetry(explicit)
    assert explicit["MEM0_TELEMETRY"] == "True"


def test_config_pins_history_db_under_repo_data():
    """✅ D-65（丙-13）：mem0 稽核檔固定進 repo 的 data/mem0/，不落執行機家目錄。"""
    config = build_mem0_config(load_settings(_ENV))
    from pathlib import Path

    assert Path(config["history_db_path"]).parts[-3:] == ("data", "mem0", "history.db")


class _StubEmbedder:
    def embed(self, text, memory_action=None):
        return [0.0]


class _StubVectorStore:
    def search(self, query, vectors, top_k=5, filters=None):
        return ["hit"]


class _StubReranker:
    def rerank(self, query, documents, top_k=None):
        return documents


class _StubMemory:
    def __init__(self, reranker=None):
        self.embedding_model = _StubEmbedder()
        self.vector_store = _StubVectorStore()
        self.reranker = reranker


def test_instrument_tracing_passthrough_when_disabled():
    """停用時所有包裝點必須是 identity——行為與未包裝一字不差。"""
    tracing_client.reset_for_test()
    memory = _StubMemory(reranker=_StubReranker())
    assert _instrument_tracing(memory) is memory
    assert memory.embedding_model.embed("你好", "search") == [0.0]
    assert memory.vector_store.search(query="q", vectors=[0.1]) == ["hit"]
    assert memory.reranker.rerank("q", ["d"], 1) == ["d"]


def test_instrument_tracing_span_names_and_capture_policy(monkeypatch):
    """三個包裝點的 span 名與 capture 策略（2026-07-30 spec）：向量／候選集不進 span。"""
    import opik

    tracing_client.reset_for_test()
    seen: list[dict] = []
    monkeypatch.setattr(opik, "track", lambda **kw: (seen.append(kw), lambda f: f)[1])
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)
    memory = _instrument_tracing(_StubMemory(reranker=_StubReranker()))
    memory.embedding_model.embed("你好", "search")
    memory.vector_store.search(query="q", vectors=[0.1])
    memory.reranker.rerank("q", ["doc"], 1)
    by_name = {kw["name"]: kw for kw in seen}
    assert by_name["mem0_embed"]["capture_output"] is False
    assert by_name["mem0_vector_search"]["ignore_arguments"] == ["vectors"]
    assert by_name["mem0_vector_search"]["capture_output"] is False
    assert by_name["mem0_rerank"]["ignore_arguments"] == ["documents"]
    assert by_name["mem0_rerank"]["capture_output"] is False


def test_instrument_tracing_skips_absent_reranker(monkeypatch):
    """LONGTERM_RERANK_ENABLED=false 時 reranker 是 None：只包兩處、不炸。"""
    import opik

    tracing_client.reset_for_test()
    seen: list[dict] = []
    monkeypatch.setattr(opik, "track", lambda **kw: (seen.append(kw), lambda f: f)[1])
    monkeypatch.setattr(tracing_decorators, "is_enabled", lambda: True)
    memory = _instrument_tracing(_StubMemory(reranker=None))
    memory.embedding_model.embed("你好", "search")
    memory.vector_store.search(query="q", vectors=[0.1])
    assert {kw["name"] for kw in seen} == {"mem0_embed", "mem0_vector_search"}


def test_instrument_tracing_survives_missing_attributes():
    """mem0 升版屬性改名時：warning 後原樣回傳，觀測絕不可壞掉記憶功能。"""

    class _Weird:
        pass

    weird = _Weird()
    assert _instrument_tracing(weird) is weird


def test_build_mem0_memory_instruments_instance(monkeypatch):
    """工廠出貨的實例必須已經過包裝（接線驗證，不連真庫）。"""
    import mem0

    stub = _StubMemory()
    monkeypatch.setattr(mem0.Memory, "from_config", staticmethod(lambda cfg: stub))
    from kinsun.memory.longterm.mem0_factory import build_mem0_memory

    assert build_mem0_memory(load_settings(_ENV)) is stub


def test_reranker_config_present_when_enabled():
    """✅ D-40（丁-4）：reranker 走 gemini LLM reranker；關閉時整塊不出現。"""
    on = build_mem0_config(load_settings({**_ENV, "LONGTERM_RERANK_ENABLED": "true"}))
    assert on["reranker"]["provider"] == "llm_reranker"
    assert on["reranker"]["config"]["provider"] == "gemini"
    off = build_mem0_config(load_settings({**_ENV, "LONGTERM_RERANK_ENABLED": "false"}))
    assert "reranker" not in off
