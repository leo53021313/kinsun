from kinsun.config import load_settings
from kinsun.longterm.provenance import CUSTOM_FACT_EXTRACTION_PROMPT
from kinsun.mem0_factory import build_mem0_config

_ENV = {
    "LINE_CHANNEL_SECRET": "s",
    "LINE_CHANNEL_ACCESS_TOKEN": "t",
    "GEMINI_API_KEY": "k",
    "GEMINI_MODEL": "gemini-x",
    "EMBEDDING_MODEL": "models/gemini-embedding-001",
    "DATABASE_URL": "postgresql://u:p@h:5432/db",
    "NEO4J_URI": "neo4j+s://x",
    "NEO4J_USERNAME": "neo4j",
    "NEO4J_PASSWORD": "pw",
}


def test_build_mem0_config_shape():
    cfg = build_mem0_config(load_settings(_ENV))
    assert cfg["llm"]["provider"] == "gemini"
    assert cfg["llm"]["config"]["model"] == "gemini-x"
    assert cfg["embedder"]["provider"] == "gemini"
    assert cfg["vector_store"]["provider"] == "supabase"
    assert cfg["vector_store"]["config"]["connection_string"] == "postgresql://u:p@h:5432/db"
    assert cfg["graph_store"]["provider"] == "neo4j"
    assert cfg["graph_store"]["config"]["url"] == "neo4j+s://x"


def test_build_mem0_config_includes_custom_instructions():
    cfg = build_mem0_config(load_settings(_ENV))
    assert cfg["custom_instructions"] == CUSTOM_FACT_EXTRACTION_PROMPT
