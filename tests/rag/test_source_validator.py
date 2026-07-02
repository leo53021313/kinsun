from kinsun.rag.source_registry import SourceRegistry
from kinsun.rag.source_validator import SourceValidator


def test_approved_government_source_can_ingest():
    source = SourceRegistry().get("hpa_elder_health")

    result = SourceValidator().validate(source)

    assert result.can_ingest is True
    assert result.issues == ()


def test_conditional_source_cannot_ingest_until_reviewed():
    source = SourceRegistry().get("health99")

    result = SourceValidator().validate(source)

    assert result.can_ingest is False
    assert "來源尚未核准進入衛教 RAG。" in result.issues
    assert "授權狀態為 needs_review。" in result.issues


def test_rejected_hospital_source_is_blocked():
    source = SourceRegistry().get("cgmh")

    result = SourceValidator().validate(source)

    assert result.can_ingest is False
    assert "來源驗證狀態為 rejected。" in result.issues
    assert "授權狀態為 disallowed。" in result.issues
