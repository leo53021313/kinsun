from kinsun.rag.schemas import ContentPolicy, SourceRole
from kinsun.rag.source_registry import SourceRegistry
from kinsun.rag.source_validator import SourceValidator


def test_approved_government_source_can_ingest():
    source = SourceRegistry().get("hpa_health_education")

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


def test_hpa_articles_come_from_a_single_sitemap_source():
    """國健署整站只留一個 sitemap 驅動的來源。

    先前四個來源（銀髮族健康、老人健康促進、慢性病防治、常見問答）各自從
    List.aspx 爬連結，2026-08-01 實測發現三者收回來的文章落在同一批 nodeid——
    那些是頁尾共用連結，主題區隔等於零。四個來源指向同一份 sitemap 更沒有意義：
    會對政府網站發出四倍請求，而跨來源 URL 去重會把後三份成果全部丟棄。
    """
    registry = SourceRegistry()
    approved = {source.source_id for source in registry.approved_for_rag()}

    hpa = registry.get("hpa_health_education")
    assert hpa.sitemap_url == "https://www.hpa.gov.tw/sitemap.xml"
    assert hpa.content_url_pattern == r"Detail\.aspx"
    assert hpa.source_id in approved

    for retired in ("hpa_elder_health", "hpa_elder_chronic", "hpa_chronic_disease", "hpa_faq"):
        assert retired not in approved, f"{retired} 已由 hpa_health_education 取代"


def test_sources_without_sitemap_still_crawl_links():
    """沒有 sitemap 的站台（cdc 實測 404）維持既有的爬連結路徑。"""
    registry = SourceRegistry()

    assert registry.get("cdc_advocacy").sitemap_url == ""
