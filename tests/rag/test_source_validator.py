from kinsun.rag.source_registry import SourceRegistry
from kinsun.rag.source_validator import SourceValidator


def test_approved_government_source_can_ingest():
    source = SourceRegistry().get("hpa_elder_health")

    result = SourceValidator().validate(source)

    assert result.can_ingest is True
    assert result.issues == ()


def test_conditional_source_can_ingest_for_noncommercial_demo():
    source = SourceRegistry().get("health99")

    result = SourceValidator().validate(source)

    assert result.can_ingest is True
    assert result.issues == ()


def test_hospital_source_can_ingest_but_keeps_license_metadata():
    source = SourceRegistry().get("cgmh")

    result = SourceValidator().validate(source)

    assert result.can_ingest is True
    assert source.copyright_status == "disallowed"
