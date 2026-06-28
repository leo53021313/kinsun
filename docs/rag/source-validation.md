# 衛教 RAG 資料來源驗證報告

驗證日期：2026-06-29（Asia/Taipei）

本報告只驗證使用者提供的候選來源，不自行新增資料來源。結論分成：

- `approved`：來源身份、技術可用性、授權跡象與內容型態足以先進入受控 ingestion。
- `conditional`：可信，但需人工確認授權、單篇品質、解析品質或更新機制後才可 ingestion。
- `rejected`：目前不建議 ingestion。
- `out_of_scope`：與衛教 RAG 內容庫不直接相關，可作為未來查詢或營運資料。

重要限制：

- 本報告不是法律意見。任何 `approved` 來源在正式上線前仍需保留授權截圖或頁面快照。
- 醫院來源即使醫療可信度高，只要沒有明確再利用授權，就不可直接全文索引。
- 圖片型海報、掃描 PDF、影片逐字稿不列入第一批 ingestion，除非 OCR 與人工抽驗通過。
- 疫苗、用藥、治療準則、傳染病疫情資訊需額外標記時效與重新審查週期。

## 驗證依據

- 使用 `Invoke-WebRequest` 於 2026-06-29 檢查候選 URL HTTP 狀態、標題與可讀文字片段。
- 檢查各網域 `robots.txt`：HPA、Health99、MOHW、CDC、FDA、NHI、MedlinePlus、WHO 有可讀 robots；部分 API 或醫院子站沒有 robots 或回 404。
- 檢查頁尾／條款跡象：
  - HPA 有「政府網站資料開放宣告」。
  - Health99 有「政府網站資料開放宣告」與「網站管理規範與著作權聲明」。
  - MOHW 有「政府網站資料開放宣告」。
  - CDC 有「著作權聲明」與「政府網站資料開放宣告」。
  - FDA 有「著作權聲明」與「網站資料開放宣告」。
  - data.gov.tw 提供「政府資料開放授權條款－第 1 版」。
  - WHO 著作權頁說明多數出版品採 CC BY-NC-SA 3.0 IGO，但翻譯、圖表、商標與特定素材有條件限制。
  - 長庚首頁明確標示網站內容未經授權禁止轉載。

## 驗證結論表

| source_id | title | url_or_file | publisher | source_type | medical_trust_level | copyright_status | freshness_status | extraction_difficulty | recommended_status | reason | required_action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hpa_elder_health | 銀髮族健康 | https://www.hpa.gov.tw/Pages/List.aspx?nodeid=39 | 衛生福利部國民健康署 | government | high | allowed | 需定期重抓，慢病與長者照護需人工審查日期 | medium | approved | 官方長者衛教入口，2026-06-29 可取得 HTML，適合台灣長輩場景。 | 建立 per-page ingestion，只收有標題、日期、發布單位的文章。 |
| hpa_elder_chronic | 老人健康促進及慢性疾病防治 | https://www.hpa.gov.tw/Pages/List.aspx?nodeid=40 | 衛生福利部國民健康署 | government | high | allowed | 需定期重抓，慢病內容需記錄版本與日期 | medium | approved | 官方慢病與老人健康促進資訊，與本專案高度相關。 | 設定 topic whitelist，避免抓到活動公告型內容。 |
| hpa_chronic_disease | 慢性病防治 | https://www.hpa.gov.tw/Pages/List.aspx?nodeid=46 | 衛生福利部國民健康署 | government | high | allowed | 高時效敏感，慢病數值需定期 review | medium | approved | 官方慢性病防治來源，適合一般衛教與自我照護。 | 以 source_updated_at、last_reviewed_at 控管過期風險。 |
| hpa_handbooks | 健康手冊專區 | https://www.hpa.gov.tw/Pages/EBookList.aspx?nodeid=53 | 衛生福利部國民健康署 | government | high | needs_review | 手冊版本需逐本記錄 | high | conditional | 官方手冊可信，但多為 PDF／電子書，解析與版次需逐本確認。 | 只允許文字型 PDF；掃描檔需 OCR 與人工抽驗。 |
| hpa_posters_leaflets | 衛教宣導海報及單張專區 | https://www.hpa.gov.tw/Pages/EBookList.aspx?nodeid=54 | 衛生福利部國民健康署 | government | high | needs_review | 宣導素材可能隨政策更新 | high | conditional | 官方素材可信，但多為圖像或 PDF，OCR 成本高，且圖表素材授權需逐件確認。 | 第一階段不 ingestion 圖片型海報；保留人工審查流程。 |
| hpa_faq | 常見問答 | https://www.hpa.gov.tw/Pages/List.aspx?nodeid=80 | 衛生福利部國民健康署 | government | high | allowed | 問答需定期重抓 | medium | approved | 官方 FAQ 可讀性高，適合一般民眾衛教。 | 建立 FAQ parser，保留問題、答案、日期與 URL。 |
| health99 | 健康九九＋ | https://health99.hpa.gov.tw/ | 衛生福利部國民健康署 | government | high | needs_review | 影音、活動與素材混合，需 per-item freshness | high | conditional | 官方健康資源入口可信，但包含影音、下載、圖片與活動內容，解析品質差異大。 | 先只收可取得乾淨 HTML 或文字型附件；其餘逐件審核。 |
| mohw_health_window | 衛教視窗 | https://www.mohw.gov.tw/np-34-1.html | 衛生福利部 | government | high | allowed | 政策與衛教文章需定期重抓 | medium | approved | 衛福部官方衛教入口，2026-06-29 可取得 HTML。 | 只收衛教文章，不收新聞稿式宣傳或外部連結。 |
| mohw_health_article | 衛福部衛教內容頁 | https://www.mohw.gov.tw/cp-88-210-1.html | 衛生福利部 | government | high | allowed | 需記錄發布／更新日期 | medium | approved | 屬衛福部官方內容頁，可信度高。 | ingestion 時驗證標題、日期、發布單位，不符合則略過。 |
| mohw_health_list | 衛福部衛教列表 | https://www.mohw.gov.tw/lp-88-1-40.html | 衛生福利部 | government | high | allowed | 列表需定期重抓 | medium | approved | 官方列表可作為 discovery 入口。 | 只用於發現子頁，子頁仍需逐頁驗證 metadata。 |
| cdc_home | 疾病管制署入口 | https://www.cdc.gov.tw/ | 衛生福利部疾病管制署 | government | high | allowed | 傳染病資訊高度時效敏感 | medium | conditional | 官方高可信，但首頁不是衛教文件；傳染病內容需嚴格時效控管。 | 建立傳染病 topic whitelist 與 refresh SLA。 |
| cdc_advocacy | CDC 宣導 | https://www.cdc.gov.tw/Advocacy | 衛生福利部疾病管制署 | government | high | needs_review | 宣導素材需逐件審查 | high | conditional | 官方宣導素材可信，但常含圖片、PDF、影片與特定著作權聲明。 | 需逐件確認授權與文字可抽取性，暫不批次 ingestion。 |
| fda_home | 食品藥物管理署入口 | https://www.fda.gov.tw/ | 衛生福利部食品藥物管理署 | government | high | allowed | 食藥安全資訊可能快速過期 | medium | conditional | 官方食藥安全來源可信，但首頁與多數內容不是一般衛教文章。 | 建立食品安全、藥品安全 topic whitelist；禁止用來產生用藥調整建議。 |
| hpa_news_api | HPA 新聞 API | https://www.hpa.gov.tw/wf/newsapi.ashx | 衛生福利部國民健康署 | government | high | allowed | 新聞高度時效敏感 | low | conditional | API 可取得 JSON，技術可用性高；但新聞不等於穩定衛教。 | 僅作官方更新來源，需人工標記可轉為衛教知識的項目。 |
| hpa_rss_index | HPA RSS 專區 | https://www.hpa.gov.tw/Pages/List.aspx?nodeid=1348 | 衛生福利部國民健康署 | government | high | allowed | feed 需定期輪詢 | low | approved | 官方 RSS 索引適合作 discovery 與更新偵測。 | 不直接作回答來源；只記錄 feed 與 discovered documents。 |
| cdc_rss | CDC RSS | https://www.cdc.gov.tw/RSS | 衛生福利部疾病管制署 | government | high | allowed | 傳染病與新聞 feed 需頻繁 refresh | low | approved | 官方 RSS 可用於更新偵測。 | 不直接作回答來源；子項目仍需逐篇驗證。 |
| fda_open_data | FDA open data API | https://data.fda.gov.tw/ | 衛生福利部食品藥物管理署 | government | high | allowed | dataset 需記錄版本與更新日 | low | conditional | Swagger UI 可用，屬結構化資料；但各 dataset 不一定是衛教內容。 | 逐 dataset 審查欄位、授權與是否適合長輩衛教。 |
| nhi_open_page | 健保署資料開放頁 | https://www.nhi.gov.tw/ch/np-3036-1.html | 衛生福利部中央健康保險署 | government | high | needs_review | URL 對本驗證環境回 403 | high | conditional | 官方來源可信，但 2026-06-29 以本驗證方式回 403，且健保資料多偏給付與行政。 | 人工確認可存取路徑與資料用途；預設不進衛教回答庫。 |
| nhi_iode | 健保署資料開放平台 | https://info.nhi.gov.tw/IODE0000/IODE0000S01 | 衛生福利部中央健康保險署 | government | high | needs_review | dataset 需逐項確認 | medium | out_of_scope | 官方結構化資料平台，較偏行政、給付與機構資訊，不是一般衛教知識。 | 可保留給未來查詢服務，不放入衛教 RAG 第一批。 |
| data_gov_tw | 政府資料開放平臺 | https://data.gov.tw/ | 國家發展委員會／各資料提供機關 | government | medium | allowed | 取決於各 dataset | medium | conditional | 平台授權清楚，但不是醫療出版單位；醫療可信度需回到提供機關與 dataset。 | 只作 dataset discovery；逐 dataset 驗證 publisher、欄位與授權。 |
| data_gov_m2m | 政府資料開放 M2M | https://data.gov.tw/m2m | 國家發展委員會／各資料提供機關 | government | medium | allowed | API 資料需定期 refresh | low | conditional | 適合機器抓取，但內容是否屬衛教需逐 dataset 判斷。 | 不直接回答；建立 dataset-level registry。 |
| vghtpe_ihealth | 北榮健康 e 點通 | https://ihealth.vghtpe.gov.tw/ | 臺北榮民總醫院 | hospital | high | needs_review | 本驗證環境首頁回 403 | high | conditional | 醫院可信度高，但本次自動存取受阻，授權與解析品質未確認。 | 人工確認實際衛教 URL、授權與是否允許索引。 |
| ntuh_epaper | 臺大醫院健康電子報 | https://epaper.ntuh.gov.tw/health/ | 國立臺灣大學醫學院附設醫院 | hospital | high | disallowed | 文章有期數與日期，需版本記錄 | medium | rejected | 醫院可信度高，但未見可批次再利用授權，健康電子報通常受著作權保護。 | 未取得書面授權前不可 ingestion；僅可人工閱讀與引用連結。 |
| cgmh | 長庚醫療財團法人 | https://www.cgmh.org.tw/ | 長庚醫療財團法人 | hospital | high | disallowed | 醫院衛教需逐頁確認 | high | rejected | 首頁明確標示網站內容未經授權禁止轉載；候選 URL 也不是具體衛教頁。 | 需取得授權並確認具體衛教頁後，才可重新評估。 |
| cmuh | 中國醫藥大學附設醫院 | https://www.cmuh.cmu.edu.tw/ | 中國醫藥大學附設醫院 | hospital | high | needs_review | 需確認具體衛教頁與日期 | high | conditional | 醫院可信，但候選 URL 只是入口，授權與實際衛教頁未確認。 | 先列候選 allowlist，不開 crawler；人工確認 URL 與授權。 |
| vghtc | 臺中榮民總醫院 | https://www.vghtc.gov.tw/ | 臺中榮民總醫院 | hospital | high | needs_review | 網站內容動態載入，需確認文章日期 | high | conditional | 醫院可信，但候選 URL 為首頁，且頁面含大量動態與新聞內容。 | 先列候選 allowlist，不開 crawler；確認衛教分類與授權。 |
| medlineplus | MedlinePlus | https://medlineplus.gov/ | U.S. National Library of Medicine | government | high | needs_review | 英文內容需翻譯與定期更新 | medium | conditional | 國際官方高可信，提供開發者資料與 XML；但英文、頁面來源與著作權需逐項確認。 | 只作國際補充；避免自行翻譯醫療指引，需標記語言與版本。 |
| who_health_topics | WHO Health Topics | https://www.who.int/health-topics | World Health Organization | international_official | high | needs_review | 國際資訊需確認是否適合台灣長輩 | medium | conditional | WHO 高可信，著作權頁顯示多數出版品採 CC BY-NC-SA 3.0 IGO，但翻譯與素材有條件。 | 法務確認授權、翻譯與 attribution 後，只作補充來源。 |

## 第一批建議 ingestion 順序

1. HPA HTML 頁：`hpa_elder_health`、`hpa_elder_chronic`、`hpa_chronic_disease`、`hpa_faq`。
2. MOHW HTML 衛教頁：`mohw_health_window`、`mohw_health_article`、`mohw_health_list`。
3. RSS／API discovery：`hpa_rss_index`、`cdc_rss`，只作更新偵測，不直接回答。

暫緩 ingestion：

- PDF、圖片、海報、電子報、醫院首頁、影片、新聞 API 全量內容。
- 任何沒有明確標題、日期、發布單位、URL、授權狀態的內容。
- 任何涉及診斷、治療選擇、用藥調整、急症判斷的內容。

## 後續必要決策

- 指派人工資料治理負責人，保留授權截圖與驗證紀錄。
- 定義「正式可用衛教文件」審查表。
- 決定第一批主題：建議先做長者運動、睡眠、飲食、慢病自我照護與預防保健。
- 決定 refresh 週期：一般衛教每 90 天；傳染病、疫苗、藥品安全每 7 至 30 天或事件觸發。
