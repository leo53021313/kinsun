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


def test_order_answer_first_puts_answer_sources_before_discovery():
    """跨來源去重是先到先得，故 ANSWER 必須排在 DISCOVERY 之前。

    否則同一個 URL 被 discovery 來源先claim走，該頁只留 membership／稽核、
    不建回答向量，衛教內文等於憑空消失（2026-07-29 跨來源重複修復的前提）。
    """
    from kinsun.rag.schemas import SourceRole
    from kinsun.rag.source_registry import order_answer_first

    registry = SourceRegistry()
    # 刻意把 discovery 排前面
    ids = ("hpa_rss_index", "hpa_elder_health", "cdc_home", "cdc_advocacy")

    ordered = order_answer_first(ids, registry)

    roles = [registry.get(sid).role for sid in ordered]
    assert roles == sorted(roles, key=lambda r: r != SourceRole.ANSWER)
    assert set(ordered) == set(ids), "只調順序，不可增刪來源"
    # 同一角色內維持原有相對順序（穩定排序，避免每輪 claim 歸屬跳動）
    assert ordered.index("hpa_elder_health") < ordered.index("cdc_advocacy")
