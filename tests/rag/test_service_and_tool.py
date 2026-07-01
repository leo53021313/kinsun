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


def test_rag_tool_returns_json_payload():
    service = HealthEducationRagService(
        _FakeRetriever((_result("高血壓照護包含規律量血壓。"),)),
    )
    output = build_health_rag_handler(service)({"query": "高血壓"})

    assert '"safety_level": "normal"' in output
    assert "衛生福利部國民健康署" in output


def test_rag_service_does_not_retrieve_when_risk_signal_is_present():
    retriever = _FakeRetriever((_result("胸痛衛教。"),))
    service = HealthEducationRagService(retriever)

    answer = service.answer("胸口很痛又喘不過氣", has_risk_signal=True)

    assert retriever.queries == []
    assert answer.should_escalate_to_risk_engine is True
