"""候選衛教資料來源清冊。

這份清冊只保存治理狀態；是否實際抓取仍需通過 SourceValidator。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

from kinsun.rag.schemas import (
    CopyrightStatus,
    RecommendedStatus,
    Source,
    SourceRole,
    SourceType,
    TrustLevel,
)

DISCOVERY_SOURCE_IDS = frozenset(
    {
        "mohw_health_list",
        "cdc_home",
        "fda_home",
        "hpa_news_api",
        "hpa_rss_index",
        "cdc_rss",
        "fda_open_data",
        "data_gov_tw",
        "data_gov_m2m",
    }
)

DEFAULT_SOURCES: tuple[Source, ...] = (
    Source(
        "hpa_health_education",
        "國民健康署衛教文章",
        "https://www.hpa.gov.tw/",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.APPROVED,
        True,
        ("hpa.gov.tw",),
        "國民健康署整站衛教文章，清單取自 sitemap.xml（5,667 篇），"
        "實際收錄與否由 content_filter 逐篇判定。",
        content_url_pattern=r"Detail\.aspx",
        sitemap_url="https://www.hpa.gov.tw/sitemap.xml",
    ),
    # 以下四個來源已由 hpa_health_education 取代（2026-08-01）。
    # 它們各自從 List.aspx 爬連結，但國健署每頁都渲染全站 225 個分類選單，
    # 實測三者收回來的文章落在同一批 nodeid（頁尾共用連結），主題區隔等於零。
    # 保留條目供稽核與歷史追溯，approved_for_rag 設 False 不再收錄。
    Source(
        "hpa_elder_health",
        "銀髮族健康",
        "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=39",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.OUT_OF_SCOPE,
        False,
        ("hpa.gov.tw",),
        "已併入 hpa_health_education；此列表頁本身沒有自己的文章。",
    ),
    Source(
        "hpa_elder_chronic",
        "老人健康促進及慢性疾病防治",
        "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=40",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.OUT_OF_SCOPE,
        False,
        ("hpa.gov.tw",),
        "已併入 hpa_health_education。",
    ),
    Source(
        "hpa_chronic_disease",
        "慢性病防治",
        "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=46",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.OUT_OF_SCOPE,
        False,
        ("hpa.gov.tw",),
        "已併入 hpa_health_education。",
    ),
    Source(
        "hpa_handbooks",
        "健康手冊專區",
        "https://www.hpa.gov.tw/Pages/EBookList.aspx?nodeid=53",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.CONDITIONAL,
        True,
        ("hpa.gov.tw",),
        "PDF／電子書需逐本確認解析品質與版本。",
    ),
    Source(
        "hpa_posters_leaflets",
        "衛教宣導海報及單張專區",
        "https://www.hpa.gov.tw/Pages/EBookList.aspx?nodeid=54",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.CONDITIONAL,
        True,
        ("hpa.gov.tw",),
        "圖片型素材與 PDF 需人工確認。",
    ),
    Source(
        "hpa_faq",
        "常見問答",
        "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=80",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.OUT_OF_SCOPE,
        False,
        ("hpa.gov.tw",),
        "已併入 hpa_health_education；問答文章同樣在 sitemap 的 Detail.aspx 底下。",
    ),
    Source(
        "health99",
        "健康九九＋",
        "https://health99.hpa.gov.tw/",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.APPROVED,
        True,
        ("health99.hpa.gov.tw",),
        "國健署官方衛教入口；文字內容依政府網站資料開放宣告使用"
        "（Leo 核定 2026-07-27），影音下載素材仍不抓取。",
    ),
    Source(
        "hpa_sleep_handbook",
        "睡眠與精神健康（國民健康署衛教手冊）",
        "https://health.hpa.gov.tw/common/Download.ashx"
        "?f=f70fe5f8-cf1f-4f89-929c-072a219d29ab.pdf"
        "&o=05.%E7%9D%A1%E7%9C%A0%E8%88%87%E7%B2%BE%E7%A5%9E%E5%81%A5%E5%BA%B7.pdf",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.APPROVED,
        True,
        ("health.hpa.gov.tw",),
        "國健署健康職場資訊網的衛教手冊，文字型 PDF（非掃描檔），實測抽出 18,968 字，"
        "涵蓋失眠盛行率、致病原因、對生活的影響、治療與注意事項。"
        "2026-08-02 新增（Leo 核定）：長者睡眠衛教在既有來源全數落空——國健署 sitemap "
        "的 5,667 篇裡標題含「睡」「眠」的 14 篇全是嬰兒猝死與寶寶睡姿，"
        "衛福部那兩篇對的埋在焦點新聞第 1,094 頁分頁裡爬不到。"
        "⚠️ 單一檔案來源：PDF 本身沒有連結，爬取到此為止；檔案 30 MB，每次週更會重抓。",
    ),
    Source(
        "mohw_health_education",
        "衛生福利部衛教內容",
        "https://www.mohw.gov.tw/lp-88-1-40.html",
        "衛生福利部",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.APPROVED,
        True,
        ("mohw.gov.tw",),
        "衛生福利 e 寶箱底下的 30 個主題頁（用藥安全、健康促進、醫療照護、傳染病防治、"
        "中醫藥⋯⋯），各 1,100～1,800 字，子連結只有頁尾，主題頁本身即是內容。",
        content_url_pattern=r"cp-88-\d+",
    ),
    # 以下三個來源已由 mohw_health_education 取代（2026-08-05，Leo 核定）。
    # 實測三者收回來的全是「109年衛生福利部新聞」這類年度索引頁、零篇內文；
    # 又同爬一個網域，跨來源去重先到先得，後兩者的成果互相抵銷。
    # 保留條目供稽核與歷史追溯，approved_for_rag 設 False 不再收錄。
    Source(
        "mohw_health_window",
        "衛教視窗",
        "https://www.mohw.gov.tw/np-34-1.html",
        "衛生福利部",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.OUT_OF_SCOPE,
        False,
        ("mohw.gov.tw",),
        "已併入 mohw_health_education；種子頁 np-34-1.html 標題雖是「衛教視窗」，"
        "整頁只有站台選單與頁尾、沒有任何文章連結。",
    ),
    Source(
        "mohw_health_article",
        "衛福部衛教內容頁",
        "https://www.mohw.gov.tw/cp-88-210-1.html",
        "衛生福利部",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.OUT_OF_SCOPE,
        False,
        ("mohw.gov.tw",),
        "已併入 mohw_health_education；這是 e 寶箱底下的單一主題頁，不需要獨立來源。",
    ),
    Source(
        "mohw_health_list",
        "衛福部衛教列表",
        "https://www.mohw.gov.tw/lp-88-1-40.html",
        "衛生福利部",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.OUT_OF_SCOPE,
        False,
        ("mohw.gov.tw",),
        "已併入 mohw_health_education——同一個種子頁，改以 ANSWER 角色收錄主題頁內文。",
    ),
    Source(
        "cdc_home",
        "疾病管制署入口",
        "https://www.cdc.gov.tw/",
        "衛生福利部疾病管制署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.CONDITIONAL,
        True,
        ("cdc.gov.tw",),
        "傳染病資訊高度時效敏感，需 topic whitelist。",
    ),
    Source(
        "cdc_diseases",
        "疾病管制署傳染病介紹",
        "https://www.cdc.gov.tw/Disease",
        "衛生福利部疾病管制署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.APPROVED,
        True,
        ("cdc.gov.tw",),
        "疾管署傳染病介紹（含流感、侵襲性肺炎鏈球菌等長者疫苗相關疾病）；"
        "文字內容依政府網站資料開放宣告使用（Leo 核定 2026-07-27）。"
        "原為 cdc_advocacy／宣導專區，2026-08-02 改指疾病介紹並更名——"
        "宣導專區只有一個索引頁，爬回來的 17 份「文件」全是站台選單、零篇文章。",
        # 疾管署沒有 sitemap.xml（回 404），但 RSS 的 type=2 feed 列出 97 個疾病頁。
        sitemap_url="https://www.cdc.gov.tw/RSS/RssXml/M8GG46VTKYT2o1VJTKvl7A?type=2",
        content_url_pattern=r"Disease/SubIndex",
    ),
    Source(
        "cdc_vaccination",
        "疾病管制署預防接種專區",
        "https://www.cdc.gov.tw/Category/List/jEcJbcX-J8_opidAmw3dyg",
        "衛生福利部疾病管制署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.APPROVED,
        True,
        ("cdc.gov.tw",),
        "疾管署預防接種專區（成人預防接種建議時程表、疫苗簡介、公費疫苗項目與接種時程、"
        "疫苗區 Q&A），著作權依政府網站資料開放宣告，與 cdc_home／cdc_diseases 同一份。"
        "2026-08-02 新增：cdc_diseases 的傳染病介紹講的是狂犬病、天花、M痘等疾病本身，"
        "「疫苗」只出現在附件標題，全庫沒有一篇在講長者接種建議。"
        "本區沒有 RSS 也沒有 sitemap，只能走連結爬取。",
        content_url_pattern=r"Category/(?:Page|QAPage|MPage)",
    ),
    Source(
        "fda_home",
        "食品藥物管理署入口",
        "https://www.fda.gov.tw/",
        "衛生福利部食品藥物管理署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.CONDITIONAL,
        True,
        ("fda.gov.tw",),
        "需 topic whitelist，禁止用於用藥調整建議。",
    ),
    Source(
        "hpa_news_api",
        "HPA 新聞 API",
        "https://www.hpa.gov.tw/wf/newsapi.ashx",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.CONDITIONAL,
        True,
        ("hpa.gov.tw",),
        "JSON 可抓取，但新聞不等於穩定衛教。",
    ),
    Source(
        "hpa_rss_index",
        "HPA RSS 專區",
        "https://www.hpa.gov.tw/Pages/List.aspx?nodeid=1348",
        "衛生福利部國民健康署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.APPROVED,
        True,
        ("hpa.gov.tw",),
        "只作更新偵測。",
    ),
    Source(
        "cdc_rss",
        "CDC RSS",
        "https://www.cdc.gov.tw/RSS",
        "衛生福利部疾病管制署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.APPROVED,
        True,
        ("cdc.gov.tw",),
        "只作更新偵測。",
    ),
    Source(
        "fda_open_data",
        "FDA open data API",
        "https://data.fda.gov.tw/",
        "衛生福利部食品藥物管理署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.CONDITIONAL,
        True,
        ("data.fda.gov.tw",),
        "需逐 dataset 確認是否屬衛教。",
    ),
    Source(
        "nhi_open_page",
        "健保署資料開放頁",
        "https://www.nhi.gov.tw/ch/np-3036-1.html",
        "衛生福利部中央健康保險署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.CONDITIONAL,
        False,
        ("nhi.gov.tw",),
        "本次驗證回 403，且內容多偏行政資料。",
    ),
    Source(
        "nhi_iode",
        "健保署資料開放平台",
        "https://info.nhi.gov.tw/IODE0000/IODE0000S01",
        "衛生福利部中央健康保險署",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.OUT_OF_SCOPE,
        False,
        ("info.nhi.gov.tw",),
        "偏行政與給付資料，不進衛教 RAG 第一批。",
    ),
    Source(
        "data_gov_tw",
        "政府資料開放平臺",
        "https://data.gov.tw/",
        "國家發展委員會／各資料提供機關",
        SourceType.GOVERNMENT,
        TrustLevel.MEDIUM,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.CONDITIONAL,
        True,
        ("data.gov.tw",),
        "只作 dataset discovery。",
    ),
    Source(
        "data_gov_m2m",
        "政府資料開放 M2M",
        "https://data.gov.tw/m2m",
        "國家發展委員會／各資料提供機關",
        SourceType.GOVERNMENT,
        TrustLevel.MEDIUM,
        CopyrightStatus.ALLOWED,
        RecommendedStatus.CONDITIONAL,
        True,
        ("data.gov.tw",),
        "只作 API discovery。",
    ),
    Source(
        "vghtpe_ihealth",
        "北榮健康 e 點通",
        "https://ihealth.vghtpe.gov.tw/",
        "臺北榮民總醫院",
        SourceType.HOSPITAL,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.CONDITIONAL,
        True,
        ("ihealth.vghtpe.gov.tw",),
        "本次驗證首頁回 403，需人工確認授權與 URL。",
    ),
    Source(
        "ntuh_epaper",
        "臺大醫院健康電子報",
        "https://epaper.ntuh.gov.tw/health/",
        "國立臺灣大學醫學院附設醫院",
        SourceType.HOSPITAL,
        TrustLevel.HIGH,
        CopyrightStatus.DISALLOWED,
        RecommendedStatus.CONDITIONAL,
        True,
        ("epaper.ntuh.gov.tw",),
        "未取得再利用授權前不可 ingestion。",
    ),
    Source(
        "cgmh",
        "長庚醫療財團法人",
        "https://www.cgmh.org.tw/",
        "長庚醫療財團法人",
        SourceType.HOSPITAL,
        TrustLevel.HIGH,
        CopyrightStatus.DISALLOWED,
        RecommendedStatus.CONDITIONAL,
        True,
        ("cgmh.org.tw",),
        "首頁標示未經授權禁止轉載。",
    ),
    Source(
        "cmuh",
        "中國醫藥大學附設醫院",
        "https://www.cmuh.cmu.edu.tw/",
        "中國醫藥大學附設醫院",
        SourceType.HOSPITAL,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.CONDITIONAL,
        True,
        ("cmuh.cmu.edu.tw",),
        "候選入口，需人工確認衛教頁與授權。",
    ),
    Source(
        "vghtc",
        "臺中榮民總醫院",
        "https://www.vghtc.gov.tw/",
        "臺中榮民總醫院",
        SourceType.HOSPITAL,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.CONDITIONAL,
        True,
        ("vghtc.gov.tw",),
        "候選入口，需人工確認衛教頁與授權。",
    ),
    Source(
        "medlineplus",
        "MedlinePlus",
        "https://medlineplus.gov/",
        "U.S. National Library of Medicine",
        SourceType.GOVERNMENT,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.CONDITIONAL,
        True,
        ("medlineplus.gov",),
        "國際補充來源，英文與授權需逐項確認。",
    ),
    Source(
        "who_health_topics",
        "WHO Health Topics",
        "https://www.who.int/health-topics",
        "World Health Organization",
        SourceType.INTERNATIONAL_OFFICIAL,
        TrustLevel.HIGH,
        CopyrightStatus.NEEDS_REVIEW,
        RecommendedStatus.CONDITIONAL,
        True,
        ("who.int",),
        "CC BY-NC-SA 3.0 IGO 與翻譯條件需法務確認。",
    ),
)


class SourceRegistry:
    def __init__(self, sources: Iterable[Source] = DEFAULT_SOURCES) -> None:
        self._sources = {
            source.source_id: (
                replace(source, role=SourceRole.DISCOVERY)
                if source.source_id in DISCOVERY_SOURCE_IDS
                else source
            )
            for source in sources
        }

    def get(self, source_id: str) -> Source:
        return self._sources[source_id]

    def all(self) -> tuple[Source, ...]:
        return tuple(self._sources.values())

    def approved_for_rag(self) -> tuple[Source, ...]:
        return tuple(source for source in self._sources.values() if source.approved_for_rag)

    def answer_sources(self) -> tuple[Source, ...]:
        return tuple(
            source
            for source in self._sources.values()
            if source.approved_for_rag and source.role == SourceRole.ANSWER
        )


def order_answer_first(
    source_ids: Iterable[str],
    registry: SourceRegistry | None = None,
) -> tuple[str, ...]:
    """ANSWER 來源排在 DISCOVERY 之前，同角色維持原順序（穩定排序）。

    跨來源 URL 去重是「先到先得」（見 `IngestionPipeline._claim_urls`）：多個來源
    爬同一個網站時會撞到同一頁，若 discovery 來源先收走，該頁只留 membership 與
    稽核、不建回答向量，衛教內文就查不到了。故收錄順序是正確性的一部分。
    """
    registry = registry or SourceRegistry()
    return tuple(sorted(source_ids, key=lambda sid: registry.get(sid).role != SourceRole.ANSWER))
