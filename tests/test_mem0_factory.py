from kinsun.config import load_settings
from kinsun.memory.longterm.mem0_factory import _disable_telemetry, build_mem0_config
from kinsun.memory.longterm.provenance import CUSTOM_FACT_EXTRACTION_PROMPT

_ENV = {
    "LINE_CHANNEL_SECRET": "s",
    "LINE_CHANNEL_ACCESS_TOKEN": "t",
    "GEMINI_API_KEY": "k",
    "GEMINI_MODEL": "gemini-x",
    "LONGTERM_EMBEDDING_MODEL": "models/gemini-embedding-001",
    "DATABASE_URL": "postgresql://u:p@h:5432/db",
}


def test_build_mem0_config_shape():
    cfg = build_mem0_config(load_settings(_ENV))
    assert cfg["llm"]["provider"] == "gemini"
    assert cfg["llm"]["config"]["model"] == "gemini-x"
    assert cfg["embedder"]["provider"] == "gemini"
    assert cfg["vector_store"]["provider"] == "supabase"
    assert cfg["vector_store"]["config"]["connection_string"] == "postgresql://u:p@h:5432/db"
    assert "graph_store" not in cfg
    assert cfg["version"] == "v1.1"


def test_build_mem0_config_includes_custom_instructions():
    cfg = build_mem0_config(load_settings(_ENV))
    assert cfg["custom_instructions"] == CUSTOM_FACT_EXTRACTION_PROMPT


def test_build_mem0_config_sets_consistent_embedding_dims():
    """embedder 輸出維度必須與向量庫維度一致，否則向量查詢會維度不符（1536 vs 768）。"""
    cfg = build_mem0_config(load_settings(_ENV))
    embedder_dims = cfg["embedder"]["config"]["embedding_dims"]
    store_dims = cfg["vector_store"]["config"]["embedding_model_dims"]
    assert embedder_dims == store_dims == 768


def test_disable_telemetry_sets_env_only_if_absent():
    """關閉 mem0 遙測（隱私），但尊重使用者顯式設定。"""
    env = {}
    _disable_telemetry(env)
    assert env["MEM0_TELEMETRY"] == "False"
    explicit = {"MEM0_TELEMETRY": "True"}
    _disable_telemetry(explicit)
    assert explicit["MEM0_TELEMETRY"] == "True"
