"""地端嵌入服務的離線測試：既有 `/embed` 與新增的 OpenAI 相容 `/v1/embeddings`。

模型推論需 GPU，但服務層邏輯不需要——以 monkeypatch 換掉 `_embed`，在無 GPU 的
CI 上鎖住行為（比照 `test_services_asr_server.py`）。重模型延遲載入，import 本
模組不吃 torch。

⚠️ `/v1/embeddings` 的回應格式**用 openai 套件自己的型別驗證**，不是自己猜的
JSON 形狀：mem0 走 `provider="openai"` 打這個端點時，回應要先過 openai SDK 的
pydantic 反序列化才輪得到 mem0，格式差一個欄位就在 SDK 那層炸掉。用 SDK 的型別
當斷言，等於把「相容」這件事釘在對方的定義上，而不是我們的理解上。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.embedding import server as embedding_server

_FAKE_DIM = 1024


def _fake_embed(texts: list[str]) -> list[list[float]]:
    # 每段文字給一個可辨識、長度正確的向量，讓順序錯置在斷言中看得出來。
    return [[float(index)] * _FAKE_DIM for index, _ in enumerate(texts)]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(embedding_server, "_embed", _fake_embed)
    monkeypatch.setattr(embedding_server, "EMBEDDING_API_KEY", "")
    return TestClient(embedding_server.app)


# ── 既有 /embed：不可因新增端點而改變 ──────────────────────────────


def test_embed_still_returns_vectors_shape(client):
    res = client.post("/embed", json={"texts": ["阿公早安", "今天天氣好"]})
    assert res.status_code == 200
    body = res.json()
    assert body["model"] == embedding_server.EMBEDDING_MODEL_ID
    assert body["dimensions"] == _FAKE_DIM
    assert [v[0] for v in body["vectors"]] == [0.0, 1.0]


# ── 新增 /v1/embeddings：OpenAI 相容 ──────────────────────────────


def test_openai_endpoint_accepts_single_string_input(client):
    res = client.post(
        "/v1/embeddings", json={"input": "我今天早上血壓有點高", "model": "BAAI/bge-m3"}
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["index"] == 0
    assert len(body["data"][0]["embedding"]) == _FAKE_DIM


def test_openai_endpoint_preserves_batch_order(client):
    """mem0 的 `embed_batch` 依 `index` 重新排序，所以 index 必須忠實對應輸入順序。"""
    res = client.post(
        "/v1/embeddings", json={"input": ["第一句", "第二句", "第三句"], "model": "BAAI/bge-m3"}
    )
    assert res.status_code == 200
    data = res.json()["data"]
    assert [item["index"] for item in data] == [0, 1, 2]
    assert [item["embedding"][0] for item in data] == [0.0, 1.0, 2.0]


def test_openai_response_validates_against_sdk_types(client):
    """回應要能通過 openai 套件自己的 pydantic 反序列化——mem0 之前先過這一關。"""
    openai_types = pytest.importorskip("openai.types")
    res = client.post("/v1/embeddings", json={"input": ["血壓"], "model": "BAAI/bge-m3"})
    parsed = openai_types.CreateEmbeddingResponse.model_validate(res.json())
    assert parsed.data[0].embedding[0] == 0.0
    assert parsed.model == embedding_server.EMBEDDING_MODEL_ID


def test_openai_endpoint_accepts_dimensions_argument(client):
    """mem0 設了 `embedding_dims` 就會把 `dimensions` 傳下來（見 mem0 openai.py）。"""
    res = client.post(
        "/v1/embeddings",
        json={"input": "血壓", "model": "BAAI/bge-m3", "dimensions": _FAKE_DIM},
    )
    assert res.status_code == 200


def test_openai_endpoint_rejects_mismatched_dimensions(client):
    """BGE-M3 的維度固定；要求別的維度必須明著拒絕，不可悄悄回 1024 讓呼叫端誤以為截斷成功。"""
    res = client.post(
        "/v1/embeddings", json={"input": "血壓", "model": "BAAI/bge-m3", "dimensions": 768}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "unsupported_dimensions"


def test_openai_endpoint_rejects_empty_input(client):
    assert client.post("/v1/embeddings", json={"input": "  ", "model": "m"}).status_code == 400
    assert client.post("/v1/embeddings", json={"input": [], "model": "m"}).status_code == 422


def test_openai_endpoint_rejects_oversized_batch(client, monkeypatch):
    monkeypatch.setattr(embedding_server, "EMBEDDING_MAX_BATCH", 2)
    res = client.post("/v1/embeddings", json={"input": ["a", "b", "c"], "model": "m"})
    assert res.status_code == 413


# ── 用真的 openai 套件打：手工組 JSON 測不到的那一層 ──────────────


def test_real_openai_client_round_trip(client):
    """把 TestClient 注入 openai 套件，走 mem0 實際會走的那條路。

    ⚠️ 這支測試是補漏洞補出來的：上面那些手工組 JSON 的測試全綠，但真的用 openai
    套件打會拿到 400——因為**新版 SDK 未指定 encoding_format 時預設送 base64**，
    而端點原本只收 float。手工組請求永遠模擬不出「對方預設會做什麼」，只有讓真正的
    客戶端跑一遍才看得見。

    這條路徑上，SDK 會自己把 base64 解回 float，所以斷言拿到的是還原後的數值——
    等於同時驗了我們的編碼與它的解碼對得起來（dtype、位元組序）。
    """
    openai = pytest.importorskip("openai")
    sdk = openai.OpenAI(base_url="http://testserver/v1", api_key="x", http_client=client)
    res = sdk.embeddings.create(input=["第一句", "第二句"], model="BAAI/bge-m3", dimensions=1024)
    assert [d.index for d in res.data] == [0, 1]
    assert [len(d.embedding) for d in res.data] == [_FAKE_DIM, _FAKE_DIM]
    assert [d.embedding[0] for d in res.data] == [0.0, 1.0]


def test_base64_encoding_matches_openai_wire_format(client):
    """base64 必須是 float32 小端序——SDK 固定以 float32 解碼，給 float64 會維度加倍且數值全錯。"""
    import base64
    import struct

    res = client.post(
        "/v1/embeddings",
        json={"input": "血壓", "model": "m", "encoding_format": "base64"},
    )
    assert res.status_code == 200
    payload = res.json()["data"][0]["embedding"]
    assert isinstance(payload, str)
    raw = base64.b64decode(payload)
    assert len(raw) == _FAKE_DIM * 4  # float32 = 4 bytes
    assert struct.unpack(f"<{_FAKE_DIM}f", raw)[0] == 0.0


def test_float_encoding_still_returns_plain_list(client):
    """明著要 float 時回原本的數字陣列（RAG 之外若有人直接打，行為不變）。"""
    res = client.post(
        "/v1/embeddings", json={"input": "血壓", "model": "m", "encoding_format": "float"}
    )
    assert isinstance(res.json()["data"][0]["embedding"], list)


def test_unknown_encoding_format_is_rejected(client):
    res = client.post(
        "/v1/embeddings", json={"input": "血壓", "model": "m", "encoding_format": "gzip"}
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "unsupported_encoding_format"


# ── 金鑰：openai SDK 只會送 Authorization: Bearer ────────────────


def test_openai_endpoint_accepts_bearer_token(client, monkeypatch):
    """openai 套件把金鑰放在 `Authorization: Bearer`，不會送 X-Api-Key。

    兩種都收：`/embed` 的既有呼叫端（RAG）用 X-Api-Key，mem0 走 SDK 用 Bearer。
    """
    monkeypatch.setattr(embedding_server, "EMBEDDING_API_KEY", "sekret")
    payload = {"input": "血壓", "model": "m"}
    assert client.post("/v1/embeddings", json=payload).status_code == 401
    assert (
        client.post(
            "/v1/embeddings", json=payload, headers={"Authorization": "Bearer nope"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/v1/embeddings", json=payload, headers={"Authorization": "Bearer sekret"}
        ).status_code
        == 200
    )
    assert (
        client.post("/v1/embeddings", json=payload, headers={"X-Api-Key": "sekret"}).status_code
        == 200
    )


def test_embed_endpoint_still_accepts_x_api_key(client, monkeypatch):
    """新增 Bearer 支援不可讓既有的 X-Api-Key 路徑失效（RAG 用的就是它）。"""
    monkeypatch.setattr(embedding_server, "EMBEDDING_API_KEY", "sekret")
    assert client.post("/embed", json={"texts": ["a"]}).status_code == 401
    assert (
        client.post("/embed", json={"texts": ["a"]}, headers={"X-Api-Key": "sekret"}).status_code
        == 200
    )
