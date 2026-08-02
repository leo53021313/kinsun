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
    ids = ("hpa_rss_index", "hpa_elder_health", "cdc_home", "cdc_diseases")

    ordered = order_answer_first(ids, registry)

    roles = [registry.get(sid).role for sid in ordered]
    assert roles == sorted(roles, key=lambda r: r != SourceRole.ANSWER)
    assert set(ordered) == set(ids), "只調順序，不可增刪來源"
    # 同一角色內維持原有相對順序（穩定排序，避免每輪 claim 歸屬跳動）
    assert ordered.index("hpa_elder_health") < ordered.index("cdc_diseases")


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


def test_sources_without_a_content_feed_still_crawl_links():
    """沒有內容清單可讀的站台維持既有的爬連結路徑。

    衛福部的 sitemap.xml 只列出列表頁、沒有文章頁（2026-08-01 實測 403 個 loc
    全是 lp-／np- 列表），讀了也拿不到文章，因此不設 sitemap_url。
    """
    registry = SourceRegistry()

    assert registry.get("mohw_health_window").sitemap_url == ""


def test_vaccination_guidance_has_its_own_cdc_source():
    """疫苗接種指引與傳染病介紹是兩塊內容，必須分開收。

    2026-08-02 實測：`cdc_diseases`（傳染病介紹 RSS）抓回來的是狂犬病、天花、
    M痘的疾病說明，「疫苗」只出現在附件標題裡，沒有一篇在講長者接種建議。
    預防接種專區另有〈成人預防接種建議時程表〉〈成人肺炎鏈球菌疫苗接種Q&A〉
    〈流感疫苗〉等頁（實測剝除後各 2,785／3,663／3,121 字），該區沒有 RSS，
    只能走連結爬取，故不設 sitemap_url。
    """
    registry = SourceRegistry()
    source = registry.get("cdc_vaccination")

    assert source.sitemap_url == ""
    assert source.content_url_pattern == r"Category/(?:Page|QAPage|MPage)"
    assert source.source_id in {item.source_id for item in registry.approved_for_rag()}
    assert SourceValidator().validate(source).can_ingest is True


def test_elder_sleep_guidance_comes_from_a_single_handbook():
    """長者睡眠衛教全台只找得到這一份可爬的政府文件。

    2026-08-02 全庫盤點：國健署 sitemap 的 5,667 篇裡，標題含「睡」「眠」的
    14 篇全是嬰兒猝死與寶寶睡姿，零篇談長者；衛福部有兩篇對的（睡眠呼吸中止症、
    夜夜好眠）但埋在焦點新聞第 1,094 頁分頁裡，任何合理的爬取預算都到不了。
    只有健康職場資訊網的〈睡眠與精神健康〉手冊是可直接取得的完整衛教文件
    （實測 18,968 字：失眠盛行率、致病原因、對生活的影響、治療、注意事項）。
    """
    registry = SourceRegistry()
    source = registry.get("hpa_sleep_handbook")

    assert source.allowed_domains == ("health.hpa.gov.tw",)
    assert source.url.endswith(".pdf")
    assert SourceValidator().validate(source).can_ingest is True
