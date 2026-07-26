# docs/dev — 開發文件（重規劃版）

> 依老師的 VibeCoding_Workflow_Templates（完整流程模式）重新規劃的全套開發文件。
> 設計依據：[docs/superpowers/specs/2026-07-07-docs-dev全套文件重規劃-design.md](../superpowers/specs/2026-07-07-docs-dev全套文件重規劃-design.md)。
> 內容基準：**as-is＋to-be 對照**；to-be 為一次性重構的契約。
> 鐵律：所有決策由 Leo／團隊拍板，AI 不代填；未拍板一律 ⚠ 待議，登記於 [00_決策清單.md](00_決策清單.md)。

## 文件狀態表

| # | 文件 | 狀態 | 最後更新 |
| :---: | :--- | :--- | :--- |
| 00 | [決策清單](00_決策清單.md) | ✅ D-01～D-76 全回填（D-76 統一排程十二項核定、**五刀全完成**；D-38 掛起、4 項擱置；D-74 消費端完成；D-75 濫用審核採納並重寫接法；旗標預設開但支撐數字同日作廢待重跑） | 2026-07-25 |
| — | [2026-07-08 會議決策議程](2026-07-08_會議決策議程.md) | ✅ 決議已回填（會議紀錄） | 2026-07-09 |
| 02 | [專案簡報與PRD](02_專案簡報與PRD.md) | ✅ v1.4（US-C1／C2 改寫為統一排程、新增 US-C3 長輩用說的建立提醒；KPI 數值⏸實測後定；US-B3 問候自適應註記） | 2026-07-17 |
| 03 | [BDD情境](03_BDD情境.md) | ✅ 定稿（D-72 三級制已落地） | 2026-07-09 |
| 04 | [ADR（04_adr/）](04_adr/README.md) | ✅ 定稿（11 筆；ADR-003 補述 庚-54） | 2026-07-13 |
| 05 | [架構與設計](05_架構與設計.md) | ✅ v1.47（回頭查核補完六項缺口；Container 表補 RAG 週更 Worker、排程宣告集中 cron/registry.py、scheduler/→cron/ 更名；Opik 全面開啟＋日誌內容政策定案；架構對比 ref/hermes-agent 後六項邊界補強：排程工具安全界線 4、語音後端白名單、危急通知投遞三修、logging_setup、情境組裝等待上限；（新增 turn_context.turn_sources 跨層 seam 與冒名防線、危急症狀詞翻案、連線層 keepalive；TTS 分段串流（App 限定）＋回覆字數 40→30；第二批：回合內併發——情境組裝與兩道安全檢查重疊、mem0 兩次檢索並行、Gemini 逾時修復；第一批：觀測落庫與提醒標記改走 background.run、事實提供者並行查，相鄰 A/B 端到端 16.91s→11.67s；統一排程 D-76 五刀全完成：schedules 取代 medications／appointments、提醒管線改寫為單一每分鐘派送；時間改每輪注入情境、get_current_time 移除；§8.5 補濫用審核：三類越權／位置在家屬通報之後為安全屬性／誤攔防線三層；§12 離線評測四實驗；D-74 消費端） | 2026-07-27 |
| 06 | [API設計規範](06_API設計規範.md) | ✅ v1.10（`GET /admin/jobs` 母體改全系統排程宣告＋`owner`／`can_run_now` 兩欄，手動觸發跨程序回 409 `job_not_runnable_here`；`GET /admin/jobs` 逾期偵測欄位＋`never_ran`＋**逾期容許量逐 job**；新增 GET /turns/chunks/{index} 分段語音串流＋三個錯誤碼，POST /turns 回應加 chunk_count／reply_digest；統一排程 /schedules 取代 /medications 與 /appointments；新增 `GET /api/v1/admin/news` 話題新聞檢視，D-74） | 2026-07-27 |
| 07 | [模組規格與測試](07_模組規格與測試.md) | ✅ v1.46（回頭查核補完六項、總測試 2040；scheduler/→cron/＋新增 cron/registry.py 全系統排程宣告（修掉後台對 RAG 週更全盲）、build_jobs 308→123 行、transport_agent 原型移出 src/，總測試 1902；Opik capture 全開、logs 帶 trace_id；同上六項＋新增 logging_setup.py 模組列與三條寫死參數，總測試 1884；（實測四項修復：空頭承諾補救、once/weekly 判準、回退話術拆兩句、重複提問與危急黏著入提示詞，總測試 1837；逾期容許量逐 job＋後台系統頁顯示逾期告警，總測試 1832；長跑 job 走背景執行緒、`/admin/jobs` 新增 never_ran，總測試 1829；**排程停擺根因定案＝`try_claim` 浮點等值比對**（`extra_float_digits=0` 截斷 → 永久認領失敗、重啟無效），改範圍比對＋合約測試；看門狗涵蓋啟動階段、心跳檔、SIGUSR1 堆疊傾印，總測試 1824；三項修復經對抗審查修正：危急翻案只准 L0、冒名防線逐機關比對、排程器看門狗，總測試 1818；全流程模擬實測三項修復：危急症狀詞誤報、出站冒名防線、排程假死，總測試 1808；另修兩缺陷：每晚反思自 7/20 起全數失敗、/turns 佔住事件迴圈，總測試 1769；修工具結果 role 在 gemini-3.5 上全失敗、修分段 digest 來源，總測試 1767；TTS 分段串流＋speech/chunking.py；第二批：Gemini 逾時修復、mem0 檢索並行、CareAgent.prepare 情境預取，相鄰 A/B 11.13s→9.22s，總測試 1747；第一批：新增 background.py、事實提供者並行查；RAG crawler 實戰修五瑕疵：WebForms、JSON 嗅探、垃圾連結、http 升級、URL 編碼＋NUL；統一排程五刀全完成、舊模組退役） | 2026-07-27 |
| 08 | [專案結構指南](08_專案結構指南.md) | ✅ v1.17（scheduler/→cron/＋registry.py；transport_agent/ 移出 src/ 到 docs/archive/（仍在版控）、ruff 例外改掛封存區；接線三步改為「先宣告後綁定」；speech/ 補 chunking.py 回覆切句；頂層新增 background.py；schedules/ 八檔全配、medications/ 與 appointments/ 退役；頂層新增 clock.py、tools/clock.py 移除；news/fetchers 補 rss.py；admin 八頁 NewsPage） | 2026-07-27 |
| 09 | [模組依賴關係](09_模組依賴關係.md) | ✅ v1.10（cron/registry 只依賴 config，新增 app.py／rag.worker 兩條向下邊，DAG 結論不變；基礎層新增 background，零領域依賴不新增循環；Protocol 47 重掃／合約 19；濫用審核走 LLMClient seam 不新增對外依賴） | 2026-07-27 |
| 10 | [類別關係](10_類別關係.md) | ✅ v1.23（cron 群補 JobSpec 排程宣告；群 2 補 PreparedTurn 與 CareAgent.prepare，非 Protocol；FactProvider 並行呼叫但順序按注入索引；統一排程五刀全完成、舊模組類別移除；FactProvider 六段、TimeFacts 排首位；群 4 補 AbuseModerator／AbuseClassifier／ModerationResult，VoicePipeline 補選配 moderator；Protocol 47） | 2026-07-27 |
| 11 | [審查與重構指南](11_審查與重構指南.md) | ✅ v1.1（CI 已落地；docs/dev 同步鐵律入自查） | 2026-07-17 |
| 12 | [前端架構規範](12_前端架構規範.md) | ✅ v1.7（admin 話題新聞頁 D-74；web 端 React 19.2.8＋react-router 8.3） | 2026-07-25 |
| 13 | [安全與就緒檢查](13_安全與就緒檢查.md) | ✅ v1.6（日誌脫敏結案：只記系統事實、內容進 Opik；新增工具寫入授權與語音後端誤設兩列；日誌脫敏需重驗；§G 補外呼逾時與 D-22 部分落地；位置隱私列；依賴掃描與 healthz 結案） | 2026-07-27 |
| 14 | [部署與運維](14_部署與運維.md) | ✅ v1.19（**排程器模組更名，systemd unit 須重新複製一次**；九服務；排程跑在兩個程序、後台看全集；排程器 systemd unit **已安裝啟用**＋kinsun.sh 三處對齊；**排程停擺根因定案＝浮點等值比對，更正 v1.16 錯誤記載**；三層存活判讀：`status` 心跳／`/admin/jobs` 逾期／`dump` 堆疊；排程器常駐 systemd unit＋補跑爆量須知；Opik 隧道網址即時顯示；RAG 週更補 hpa 憑證 bundle 與爬深 ≥100 兩項硬前置；NEWS 白名單；Opik 服務；RAG Runbook） | 2026-07-27 |
| 15 | [文檔與維護指南](15_文檔與維護指南.md) | ✅ v1.2（同步鐵律＋前端／WBS／排程宣告三列） | 2026-07-27 |
| 16 | [WBS開發計畫](16_WBS開發計畫.md) | ✅ v1.18（新增辛-15 架構對比後六項邊界補強已完成、辛-16 第二批未施工）（辛-14 三項修復完成；辛-13 全流程模擬實測完成；辛-10 濫用審核＋辛-11 觀測與評測強化＋辛-12 防呆待施工；RAG 個人庫驗收；甲～庚結案＋辛批 10 項；⚠ 庚-09 待 Leo 確認） | 2026-07-27 |
| 17 | [前端資訊架構](17_前端資訊架構.md) | ✅ v1.11（對講機雙手勢＋admin 7 頁 D-74 話題新聞頁） | 2026-07-25 |

狀態圖例：⬜ 未開始｜🟡 進行中／待議中｜✅ 定稿

> **2026-07-10 架構文檔深化**（設計＝[spec](../superpowers/specs/2026-07-10-架構文檔深化-design.md)、計畫＝[plan](../superpowers/plans/2026-07-10-架構文檔深化.md)）：逐子系統（7 群、8 輪）深潛重構後的程式碼，回填 05／09／10／12／17；共登記 58 項後端差距（A-1～A-58，六項 HIGH 見 [05 差距彙整](05_架構與設計.md#差距與重構項本文件貢獻給-16_wbs)）與 8 項前端差距（[12 §9](12_前端架構規範.md)）。**純文檔工作，未修改任何程式碼。**

## 寫作順序

02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 12 → 17 → 11 → 13 → 14 → 15 → 16（WBS 最後，收斂全部差距項）

## 與舊文件的關係

`docs/mvp/`、`docs/全庫人工決策盤點-待議.md` 為過時參考，全套定稿後移入 `docs/archive/`；其結論一律不直接繼承。
