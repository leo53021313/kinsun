from datetime import date

from kinsun.rag.schemas import (
    Audience,
    ChunkMetadata,
    CopyrightStatus,
    DocumentChunk,
    Language,
    MedicalScope,
    SearchResult,
    SourceType,
    TrustLevel,
)
from kinsun.rag.service import HealthEducationRagService
from kinsun.tools.health_rag import build_health_rag_handler
from kinsun.tools.registry import ToolInvocationContext
from tests.fakes import FakeTraceStore


class _FakeRetriever:
    def __init__(self, results):
        self._results = results
        self.queries = []

    def retrieve(self, query: str, *, top_k: int = 5):
        self.queries.append((query, top_k))
        return self._results


def _result(text: str) -> SearchResult:
    metadata = ChunkMetadata(
        source_id="hpa_elder_health",
        document_id="doc-1",
        chunk_id="doc-1#chunk-1",
        title="高血壓衛教",
        publisher="衛生福利部國民健康署",
        source_url="https://www.hpa.gov.tw/demo",
        source_type=SourceType.GOVERNMENT,
        language=Language.ZH_TW,
        topic="高血壓",
        audience=Audience.ELDER,
        medical_scope=MedicalScope.HEALTH_EDUCATION,
        trust_level=TrustLevel.HIGH,
        approved_for_rag=True,
        copyright_status=CopyrightStatus.ALLOWED,
        source_published_at=date(2026, 1, 1),
        source_updated_at=date(2026, 1, 1),
        retrieved_at=date(2026, 6, 30),
    )
    return SearchResult(
        chunk=DocumentChunk(text=text, metadata=metadata),
        score=0.9,
        retrieval_method="vector",
    )


def test_rag_service_returns_grounded_answer_with_citation():
    service = HealthEducationRagService(
        _FakeRetriever((_result("高血壓照護包含規律量血壓。"),)),
        top_k=3,
    )

    answer = service.answer("高血壓要注意什麼？")

    assert answer.citations[0].source_id == "hpa_elder_health"
    assert "規律量血壓" in answer.answer


def test_rag_service_attaches_grounding_prompt(monkeypatch):
    """RAG grounded 改寫把 _GROUNDING_PROMPT 註冊/連結到 trace（方案 A）。"""
    from kinsun import tracing
    from kinsun.rag.service import _GROUNDING_PROMPT

    class _Llm:
        def generate(self, *, system_prompt, messages):
            return "改寫後的衛教回答"

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(tracing, "attach_prompt", lambda n, c: calls.append((n, c)))
    service = HealthEducationRagService(
        _FakeRetriever((_result("高血壓照護包含規律量血壓。"),)), llm=_Llm(), top_k=3
    )
    service.answer("高血壓要注意什麼？")
    assert ("rag_grounding", _GROUNDING_PROMPT) in calls


def test_rag_tool_returns_json_payload():
    service = HealthEducationRagService(
        _FakeRetriever((_result("高血壓照護包含規律量血壓。"),)),
    )
    output = build_health_rag_handler(service)({"query": "高血壓"})

    assert '"safety_level": "normal"' in output
    assert "規律量血壓" in output
    assert "衛生福利部國民健康署" not in output


def test_rag_service_does_not_retrieve_when_risk_signal_is_present():
    retriever = _FakeRetriever((_result("胸痛衛教。"),))
    service = HealthEducationRagService(retriever)

    answer = service.answer("胸口很痛又喘不過氣", has_risk_signal=True)

    assert retriever.queries == []
    assert answer.requires_safety_attention is True


def test_rag_tool_records_full_evidence_only_in_admin_trace():
    service = HealthEducationRagService(
        _FakeRetriever((_result("高血壓照護包含規律量血壓。"),)),
    )
    traces = FakeTraceStore()
    ticks = iter((1.0, 1.25))
    handler = build_health_rag_handler(service, traces=traces, timer=lambda: next(ticks))

    output = handler(
        {"query": "高血壓"},
        ToolInvocationContext(trace_id="trace-1", elder_id="elder-1"),
    )

    assert '"citations"' not in output
    assert traces.rag_calls[0].latency_ms == 250
    assert traces.rag_calls[0].hits[0]["retrieval_method"] == "vector"
    assert traces.rag_calls[0].citations[0]["publisher"] == "衛生福利部國民健康署"


# --- 本輪來源登記（2026-07-26 實測 S4：出站冒名防線的上游）---


def test_rag_tool_registers_citation_publishers():
    from kinsun.turn_context import turn_sources

    service = HealthEducationRagService(
        _FakeRetriever((_result("高血壓照護包含規律量血壓。"),)),
    )
    with turn_sources() as sources:
        build_health_rag_handler(service)({"query": "高血壓"})
    assert sources  # 有 citation ⇒ 有來源 ⇒ 金孫可以講出處


def test_rag_tool_registers_nothing_when_there_is_no_evidence():
    """⚠️ 對應今天的正式庫現實：沒有 active release ⇒ 零 citation ⇒ 帳本必須是空的，
    出站冒名防線因此保持武裝，模型不能靠「查過了」就冒用機關名義。"""
    from kinsun.turn_context import turn_sources

    service = HealthEducationRagService(_FakeRetriever(()))
    with turn_sources() as sources:
        build_health_rag_handler(service)({"query": "高血壓"})
    assert sources == []
