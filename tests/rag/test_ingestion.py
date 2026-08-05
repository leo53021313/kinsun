from datetime import datetime

import pytest

from kinsun.rag.embeddings import CharacterHashEmbedding
from kinsun.rag.ingestion import IngestionPipeline, SeedDocument
from kinsun.rag.source_registry import SourceRegistry


class _FakeStore:
    def __init__(self) -> None:
        self.sources = []
        self.documents = []
        self.chunks = []
        self.logs = []

    def upsert_source(self, source):
        self.sources.append(source)

    def upsert_document(self, document):
        self.documents.append(document)

    def add(self, chunk, vector):
        self.chunks.append((chunk, vector))

    def save_document(
        self,
        document,
        prepared_chunks,
        *,
        index_version,
        embedding_model_name,
        embedding_dimensions,
        fetched_at,
        parser_used,
        operator_or_job_id,
    ):
        self.documents.append(document)
        self.chunks.extend(prepared_chunks)
        self.logs.append(
            {
                "source_id": document.source_id,
                "document_id": document.document_id,
                "url": document.url,
                "fetched_at": fetched_at,
                "content_hash": document.content_hash,
                "chunk_count": len(prepared_chunks),
                "parser_used": parser_used,
                "status": "success",
                "error_message": None,
                "operator_or_job_id": operator_or_job_id,
                "index_version": index_version,
                "embedding_model_name": embedding_model_name,
                "embedding_dimensions": embedding_dimensions,
            }
        )

    def save_discovery_document(
        self,
        document,
        *,
        index_version,
        fetched_at,
        operator_or_job_id,
    ):
        self.documents.append(document)
        self.logs.append(
            {
                "source_id": document.source_id,
                "document_id": document.document_id,
                "url": document.url,
                "fetched_at": fetched_at,
                "content_hash": document.content_hash,
                "chunk_count": 0,
                "parser_used": "discovery",
                "status": "success",
                "error_message": None,
                "operator_or_job_id": operator_or_job_id,
                "index_version": index_version,
            }
        )

    def log_ingestion(self, **kwargs):
        self.logs.append(kwargs)


@pytest.mark.parametrize("max_chunk_chars", [79, 701])
def test_ingestion_rejects_chunk_limit_outside_80_to_700(max_chunk_chars):
    with pytest.raises(ValueError, match="80 到 700"):
        IngestionPipeline(
            store=_FakeStore(),
            embedding_model=CharacterHashEmbedding(dimensions=8),
            max_chunk_chars=max_chunk_chars,
        )


def test_ingestion_writes_source_document_chunks_and_audit_log():
    source = SourceRegistry().get("hpa_health_education")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        max_chunk_chars=120,
        clock=lambda: datetime(2026, 6, 30, 10, 0),
    )

    pipeline.ingest_seed_documents(
        source,
        (
            SeedDocument(
                source_id=source.source_id,
                url="https://www.hpa.gov.tw/demo",
                title="高血壓衛教",
                publisher=source.publisher,
                text="長者高血壓照護可注意規律量血壓。\n均衡飲食與活動也很重要。",
                topic="高血壓",
            ),
        ),
        operator_or_job_id="test",
    )

    assert store.sources == [source]
    assert store.documents[0].title == "高血壓衛教"
    assert store.chunks[0][0].metadata.source_id == source.source_id
    assert len(store.chunks[0][1]) == 8
    assert store.logs[0]["status"] == "success"
    assert store.logs[0]["operator_or_job_id"] == "test"


def test_ingestion_deduplicates_url_and_content_with_audit_logs():
    source = SourceRegistry().get("hpa_health_education")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        clock=lambda: datetime(2026, 6, 30, 10, 0),
    )

    pipeline.ingest_seed_documents(
        source,
        (
            SeedDocument(
                source.source_id,
                "http://www.hpa.gov.tw/demo#old",
                "舊",
                "",
                "相同衛教。",
            ),
            SeedDocument(source.source_id, "https://www.hpa.gov.tw/demo", "新", "", "相同衛教。"),
        ),
        operator_or_job_id="dedupe-test",
    )

    assert len(store.documents) == 1
    assert store.documents[0].url == "https://www.hpa.gov.tw/demo"
    assert any(log["status"] == "skipped" for log in store.logs)


def test_same_url_and_timestamp_deduplication_is_order_independent():
    source = SourceRegistry().get("hpa_health_education")

    def kept_text(seed_documents):
        store = _FakeStore()
        pipeline = IngestionPipeline(
            store=store,
            embedding_model=CharacterHashEmbedding(dimensions=8),
            clock=lambda: datetime(2026, 6, 30, 10, 0),
        )
        pipeline.ingest_seed_documents(
            source,
            seed_documents,
            operator_or_job_id="stable-dedupe-test",
        )
        return store.documents[0].text

    documents = (
        SeedDocument(source.source_id, "https://www.hpa.gov.tw/same", "甲", "", "版本甲。"),
        SeedDocument(source.source_id, "https://www.hpa.gov.tw/same", "乙", "", "版本乙。"),
    )

    assert kept_text(documents) == kept_text(tuple(reversed(documents)))


def test_ingestion_propagates_discovery_role_to_chunks():
    source = SourceRegistry().get("hpa_news_api")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
    )

    pipeline.ingest_seed_documents(
        source,
        (SeedDocument(source.source_id, source.url, "新聞", "", "健康新聞。"),),
        operator_or_job_id="role-test",
    )

    assert store.chunks[0][0].metadata.source_role.value == "discovery"


def test_versioned_discovery_document_is_audited_without_embedding():
    source = SourceRegistry().get("hpa_news_api")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
    )

    pipeline.ingest_seed_documents(
        source,
        (SeedDocument(source.source_id, source.url, "新聞", "", "健康新聞。"),),
        operator_or_job_id="role-test",
        index_version="rag-test",
    )

    assert len(store.documents) == 1
    assert store.chunks == []
    assert store.logs[0]["parser_used"] == "discovery"


def test_same_url_from_two_sources_is_ingested_once_per_run():
    """跨來源同一個 URL 只收一次。

    2026-07-29 實證：五個 HPA 來源爬同一個網站，爬深拉到 100 頁後都逛到共用的
    首頁／導覽頁，同一個 URL 被收 2～5 次——1,297 份文件只有 597 個不重複網址，
    release 的 chunk 有 47% 是重複頁面產生的（白燒嵌入配額），且結構閘門直接擋下
    （「有重複 URL；有重複內容 hash」）。既有的 deduplicate_documents 只在單一
    來源的批次內去重，看不到跨來源的重複。
    """
    registry = SourceRegistry()
    first = registry.get("hpa_health_education")
    second = registry.get("hpa_chronic_disease")
    shared_url = "https://www.hpa.gov.tw/Home/Index.aspx"
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        clock=lambda: datetime(2026, 6, 30, 10, 0),
    )

    for source in (first, second):
        pipeline.ingest_seed_documents(
            source,
            (SeedDocument(source.source_id, shared_url, "共用頁", "", "長者健康促進共用頁內容。"),),
            operator_or_job_id="cross-source-test",
        )

    kept = [d for d in store.documents if d.url == shared_url]
    assert len(kept) == 1, "同一個 URL 跨來源只能收一次"
    assert kept[0].source_id == first.source_id, "先到的來源保有該頁"
    assert any(
        log["status"] == "skipped" and log["source_id"] == second.source_id for log in store.logs
    ), "被跳過的那次必須留稽核紀錄"


def test_cross_source_claim_does_not_block_different_urls():
    """去重只針對相同 URL，不同頁面照收——別把整個來源誤殺。"""
    registry = SourceRegistry()
    first = registry.get("hpa_health_education")
    second = registry.get("hpa_chronic_disease")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        clock=lambda: datetime(2026, 6, 30, 10, 0),
    )

    for source, path in ((first, "a"), (second, "b")):
        pipeline.ingest_seed_documents(
            source,
            (
                SeedDocument(
                    source.source_id,
                    f"https://www.hpa.gov.tw/Pages/{path}.aspx",
                    "頁",
                    "",
                    f"這是第 {path} 頁的衛教內容。",
                ),
            ),
            operator_or_job_id="cross-source-test",
        )

    assert len(store.documents) == 2


def _parsed_page(url: str, title: str, text: str):
    from kinsun.rag.crawler import ParsedPage

    return ParsedPage(
        url=url,
        title=title,
        text=text,
        links=(),
        published_at=None,
        parser_used="html:test",
    )


_HPA_ARTICLE = """衛生福利部國民健康署 - 不運動就瘦不下來嗎？
跳到主要內容區塊
:::
保健闢謠
定位點
:::
首頁
>
服務園地
>
保健闢謠
不運動就瘦不下來嗎？
facebook
列印
發布單位：社區健康組
發布日期：2019/12/03
事實上相較於運動，飲食控制對減重的效果更明顯，但合併運動可以帶來更多健康益處。
運動可以有效降低體脂肪及內臟脂肪，並幫助改善血糖及血壓。
上一則
您可能會喜歡
老人家血壓太高沒關係？
回首頁"""


def test_ingest_pages_strips_page_furniture_before_chunking():
    """入庫的內文不可含導覽與文末相關文章。

    2026-08-01 盤點正式庫：10,209 個 chunk 有 61% 含導覽字樣，文末「您可能會喜歡」
    還會夾帶其他文章標題，等於把 A 文章的向量污染成 B。
    """
    source = SourceRegistry().get("hpa_health_education")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        max_chunk_chars=400,
        clock=lambda: datetime(2026, 8, 1, 10, 0),
    )

    pipeline.ingest_pages(
        source,
        (
            _parsed_page(
                "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=1",
                "衛生福利部國民健康署 - 不運動就瘦不下來嗎？",
                _HPA_ARTICLE,
            ),
        ),
        operator_or_job_id="test",
    )

    assert store.documents, "文章應被收錄"
    text = store.documents[0].text
    assert "飲食控制對減重的效果更明顯" in text
    for furniture in ("跳到主要內容區塊", ":::", "定位點", "facebook", "發布日期", "回首頁"):
        assert furniture not in text, furniture
    assert "老人家血壓太高沒關係？" not in text, "文末相關文章標題不可留在內文"


def test_ingest_pages_rejects_administrative_pages_with_audit_log():
    """行政文書不入庫，但要留稽核紀錄說明為什麼被擋。"""
    source = SourceRegistry().get("hpa_health_education")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        max_chunk_chars=400,
        clock=lambda: datetime(2026, 8, 1, 10, 0),
    )

    pipeline.ingest_pages(
        source,
        (
            _parsed_page(
                "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=913&pid=2",
                "107年國民健康署法定預算",
                "本案依相關規定辦理，詳如附件所載之內容與作業程序說明，"
                "並自公告日起生效施行，請各相關單位配合辦理查照。",
            ),
        ),
        operator_or_job_id="test",
    )

    assert store.documents == []
    assert store.chunks == []
    assert store.logs, "被擋下來的頁面仍要留稽核紀錄"
    assert store.logs[0]["status"] == "skipped"
    assert "行政文書" in store.logs[0]["error_message"]


def test_ingest_pages_strips_publisher_prefix_from_title():
    """網頁 <title> 常是「機關名 - 文章標題」，前綴要剝掉。

    2026-08-01 對真實網站煙霧測試時發現：前綴留著會讓「內文只是標題複讀」的
    判定失效（內文寫的是裸標題，比對對象卻帶著機關名），附件索引頁因此矇混過關。
    """
    source = SourceRegistry().get("hpa_health_education")
    store = _FakeStore()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        max_chunk_chars=400,
        clock=lambda: datetime(2026, 8, 1, 10, 0),
    )

    pipeline.ingest_pages(
        source,
        (
            _parsed_page(
                "https://www.hpa.gov.tw/Pages/Detail.aspx?nodeid=127&pid=5",
                f"{source.publisher} - 連喝水也會胖",
                "連喝水也會胖\n維生素、礦物質和水分不會產生熱量，但水分本是人體所需，"
                "所以正常喝水並不會增加體重，也不會產生肥肉。",
            ),
        ),
        operator_or_job_id="test",
    )

    assert store.documents[0].title == "連喝水也會胖"
    assert not store.documents[0].text.startswith("連喝水也會胖\n連喝水也會胖")


def _parsed(url: str, title: str, text: str):
    from kinsun.rag.crawler import ParsedPage

    return ParsedPage(
        url=url, title=title, text=text, links=(), published_at=None, parser_used="html:test"
    )


# 疾管署每頁都渲染整份站台骨架，且骨架用語與國健署完全不同
# （沒有「首頁 >」麵包屑、沒有「跳到主要內容區塊」），
# strip_page_furniture 的規則一個都對不上，整頁選單會原封不動進索引。
_CDC_CHROME = "\n".join(
    [
        "應用專區",
        "宣導",
        "影片",
        "(Video)",
        "海報",
        "(Poster)",
        "單張",
        "(Leaflet)",
        "授權說明",
        "網站導覽",
        "關於CDC",
        "署長簡介",
        "副署長簡介",
        "沿革與成果",
        "組織與職掌",
        "重大政策",
        "法令規章",
        "政府資料公開",
        "疫苗資訊",
        "傳染病介紹",
        "統計專區",
        "出版品",
        "1922",
        "0800-001922",
    ]
)


def test_lines_repeated_across_a_source_are_stripped_as_site_chrome():
    """同一來源多數頁面都出現的行是站台骨架，切塊前要剝掉。

    2026-08-01 實測：cdc_advocacy 收到的 17 篇「文章」其實是同一個索引頁的不同
    參數，內容 100% 是選單，卻因為長度夠而通過收錄判定，讓 38 個純導覽 chunk
    進了索引。用「跨文件重複」判定而非「行很短」或「沒有句號」——後兩者會誤殺
    衛教海報（〈高血壓〉整篇就是條列，卻是 golden set 的正解）。
    """
    store = _FakeStore()
    source = SourceRegistry().get("cdc_diseases")
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        clock=lambda: datetime(2026, 8, 2),
    )
    pages = tuple(
        _parsed(f"https://www.cdc.gov.tw/Advocacy/SubIndex/x?d={i}", "宣導", _CDC_CHROME)
        for i in range(6)
    )

    admitted = pipeline.ingest_pages(pages=pages, source=source, operator_or_job_id="job-1")

    assert admitted == ()
    assert any("未收錄" in (log.get("error_message") or "") for log in store.logs)


def test_site_chrome_stripping_keeps_bullet_style_health_posters():
    """衛教海報整篇都是條列、沒有句號，但每篇內容各不相同，不可被當成骨架剝掉。"""
    store = _FakeStore()
    source = SourceRegistry().get("cdc_diseases")
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        clock=lambda: datetime(2026, 8, 2),
    )
    # 長度比照庫裡真實的衛教海報（〈高血壓〉〈預防心血管疾病-阻塞篇〉約 45～60 字），
    # 太短的素材會撞到既有的空殼門檻，測不到本題要測的東西。
    posters = (
        "阻塞 就在一瞬間\n預防心血管疾病五招\n保持健康飲食\n規律運動\n戒菸\n定期健檢\n"
        "控制血壓血糖及血脂",
        "流感疫苗接種三重點\n每年接種一次\n65歲以上長者公費接種\n接種後留觀三十分鐘\n發燒或急性病症時暫緩接種",
        "腸病毒防治五要\n要洗手\n要通風\n要消毒\n要隔離\n要就醫並注意重症前兆\n家中有嬰幼兒者尤應留意",
        "登革熱防治重點\n清除積水容器\n每週巡倒清刷\n出現發燒與肌肉痠痛儘速就醫\n住家加裝紗窗與紗門",
        "結核病十分篩檢法\n咳嗽超過兩週\n有痰\n胸痛\n體重減輕\n食慾不振\n盜汗\n符合五分以上請儘速就醫",
        "愛滋病防治要點\n安全性行為全程使用保險套\n不共用針具\n定期篩檢及早治療\n接受治療可有效控制病毒量",
    )
    pages = tuple(
        _parsed(f"https://www.cdc.gov.tw/Disease/SubIndex/p{i}", f"衛教海報{i}", text)
        for i, text in enumerate(posters)
    )

    admitted = pipeline.ingest_pages(pages=pages, source=source, operator_or_job_id="job-2")

    assert len(admitted) == len(posters)
    assert "保持健康飲食" in admitted[0].text


def test_site_chrome_stripping_needs_enough_pages_to_be_meaningful():
    """頁面太少時不做跨文件比對——兩篇文章剛好都提到同一句不代表那是骨架。"""
    store = _FakeStore()
    source = SourceRegistry().get("cdc_diseases")
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        clock=lambda: datetime(2026, 8, 2),
    )
    shared = "接種後請留觀三十分鐘，若有不適應立即告知醫護人員並儘速就醫處理。"
    pages = (
        _parsed(
            "https://www.cdc.gov.tw/Disease/SubIndex/a", "流感疫苗", f"流感疫苗接種須知\n{shared}"
        ),
        _parsed(
            "https://www.cdc.gov.tw/Disease/SubIndex/b",
            "肺炎鏈球菌",
            f"肺炎鏈球菌疫苗接種須知\n{shared}",
        ),
    )

    admitted = pipeline.ingest_pages(pages=pages, source=source, operator_or_job_id="job-3")

    assert len(admitted) == 2
    assert all(shared in document.text for document in admitted)


def test_identical_content_under_different_urls_is_claimed_once_across_sources():
    """跨來源不只比網址，也比內容——同一份內容只收一次。

    2026-08-05 實測：`mohw_health_window` 與 `mohw_health_list` 各收到一份
    〈焦點新聞〉〈真相說明〉，網址不同但內容位元組相同。`deduplicate_documents`
    的 hash 那一關只在單一來源的批次內作用，跨來源的 claim 表又只比 canonical
    URL，兩關都放行，結構閘門直接以「有重複內容 hash」擋下整個 release。
    """
    store = _FakeStore()
    registry = SourceRegistry()
    pipeline = IngestionPipeline(
        store=store,
        embedding_model=CharacterHashEmbedding(dimensions=8),
        clock=lambda: datetime(2026, 8, 5),
    )
    text = (
        "衛生福利部焦點新聞：本部各單位發布的健康訊息與政策說明，包含疫苗接種、"
        "慢性病防治、長者照護與食品安全等主題，內容定期更新並保留發布日期。"
    )

    pipeline.ingest_pages(
        source=registry.get("mohw_health_window"),
        pages=(_parsed("https://www.mohw.gov.tw/np-16-1.html", "焦點新聞", text),),
        operator_or_job_id="job-1",
        index_version="v1",
    )
    pipeline.ingest_pages(
        source=registry.get("mohw_health_article"),
        pages=(_parsed("https://www.mohw.gov.tw/lp-16-1.html", "焦點新聞", text),),
        operator_or_job_id="job-1",
        index_version="v1",
    )

    assert [document.source_id for document in store.documents] == ["mohw_health_window"]
