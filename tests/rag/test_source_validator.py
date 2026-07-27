from kinsun.rag.schemas import ContentPolicy, SourceRole
from kinsun.rag.source_registry import SourceRegistry
from kinsun.rag.source_validator import SourceValidator


def test_approved_government_source_can_ingest():
    source = SourceRegistry().get("hpa_elder_health")

    result = SourceValidator().validate(source)

    assert result.can_ingest is True
    assert result.issues == ()


def test_conditional_source_can_ingest_for_noncommercial_demo():
    source = SourceRegistry().get("cmuh")

    result = SourceValidator(content_policy=ContentPolicy.CLASSROOM_DEMO).validate(source)

    assert result.can_ingest is True
    assert result.issues == ()


def test_hospital_source_can_ingest_but_keeps_license_metadata():
    source = SourceRegistry().get("cgmh")

    result = SourceValidator(content_policy=ContentPolicy.CLASSROOM_DEMO).validate(source)

    assert result.can_ingest is True
    assert source.copyright_status == "disallowed"


def test_safe_default_rejects_source_without_explicit_permission():
    source = SourceRegistry().get("cgmh")

    result = SourceValidator().validate(source)

    assert result.can_ingest is False
    assert "來源授權狀態為 disallowed。" in result.issues


def test_registry_marks_list_rss_api_and_data_platforms_as_discovery():
    registry = SourceRegistry()

    assert registry.get("mohw_health_list").role == SourceRole.DISCOVERY
    assert registry.get("hpa_rss_index").role == SourceRole.DISCOVERY
    assert registry.get("hpa_news_api").role == SourceRole.DISCOVERY
    assert registry.get("data_gov_tw").role == SourceRole.DISCOVERY
    assert registry.get("hpa_elder_health").role == SourceRole.ANSWER
