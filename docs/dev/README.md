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
| 05 | [架構與設計](05_架構與設計.md) | ✅ v1.42（TTS 分段串流（App 限定）＋回覆字數 40→30；第二批：回合內併發——情境組裝與兩道安全檢查重疊、mem0 兩次檢索並行、Gemini 逾時修復；第一批：觀測落庫與提醒標記改走 background.run、事實提供者並行查，相鄰 A/B 端到端 16.91s→11.67s；統一排程 D-76 五刀全完成：schedules 取代 medications／appointments、提醒管線改寫為單一每分鐘派送；時間改每輪注入情境、get_current_time 移除；§8.5 補濫用審核：三類越權／位置在家屬通報之後為安全屬性／誤攔防線三層；§12 離線評測四實驗；D-74 消費端） | 2026-07-26 |
| 06 | [API設計規範](06_API設計規範.md) | ✅ v1.6（新增 GET /turns/chunks/{index} 分段語音串流＋三個錯誤碼，POST /turns 回應加 chunk_count／reply_digest；統一排程 /schedules 取代 /medications 與 /appointments；新增 `GET /api/v1/admin/news` 話題新聞檢視，D-74） | 2026-07-26 |
| 07 | [模組規格與測試](07_模組規格與測試.md) | ✅ v1.35（修工具結果 role 在 gemini-3.5 上全失敗、修分段 digest 來源，總測試 1767；TTS 分段串流＋speech/chunking.py；第二批：Gemini 逾時修復、mem0 檢索並行、CareAgent.prepare 情境預取，相鄰 A/B 11.13s→9.22s，總測試 1747；第一批：新增 background.py、事實提供者並行查；RAG crawler 實戰修五瑕疵：WebForms、JSON 嗅探、垃圾連結、http 升級、URL 編碼＋NUL；統一排程五刀全完成、舊模組退役） | 2026-07-26 |
| 08 | [專案結構指南](08_專案結構指南.md) | ✅ v1.16（speech/ 補 chunking.py 回覆切句；頂層新增 background.py；schedules/ 八檔全配、medications/ 與 appointments/ 退役；頂層新增 clock.py、tools/clock.py 移除；news/fetchers 補 rss.py；admin 八頁 NewsPage） | 2026-07-26 |
| 09 | [模組依賴關係](09_模組依賴關係.md) | ✅ v1.9（基礎層新增 background，零領域依賴不新增循環；Protocol 47 重掃／合約 19；濫用審核走 LLMClient seam 不新增對外依賴） | 2026-07-26 |
| 10 | [類別關係](10_類別關係.md) | ✅ v1.22（群 2 補 PreparedTurn 與 CareAgent.prepare，非 Protocol；FactProvider 並行呼叫但順序按注入索引；統一排程五刀全完成、舊模組類別移除；FactProvider 六段、TimeFacts 排首位；群 4 補 AbuseModerator／AbuseClassifier／ModerationResult，VoicePipeline 補選配 moderator；Protocol 47） | 2026-07-26 |
| 11 | [審查與重構指南](11_審查與重構指南.md) | ✅ v1.1（CI 已落地；docs/dev 同步鐵律入自查） | 2026-07-17 |
| 12 | [前端架構規範](12_前端架構規範.md) | ✅ v1.7（admin 話題新聞頁 D-74；web 端 React 19.2.8＋react-router 8.3） | 2026-07-25 |
| 13 | [安全與就緒檢查](13_安全與就緒檢查.md) | ✅ v1.4（位置隱私列；依賴掃描與 healthz 結案） | 2026-07-17 |
| 14 | [部署與運維](14_部署與運維.md) | ✅ v1.15（Opik 隧道網址即時顯示；RAG 週更補 hpa 憑證 bundle 與爬深 ≥100 兩項硬前置；NEWS 白名單；Opik 服務；RAG Runbook） | 2026-07-26 |
| 15 | [文檔與維護指南](15_文檔與維護指南.md) | ✅ v1.1（同步鐵律＋前端／WBS 兩列） | 2026-07-17 |
| 16 | [WBS開發計畫](16_WBS開發計畫.md) | ✅ v1.15（辛-10 濫用審核＋辛-11 觀測與評測強化＋辛-12 防呆待施工；RAG 個人庫驗收；甲～庚結案＋辛批 10 項；⚠ 庚-09 待 Leo 確認） | 2026-07-25 |
| 17 | [前端資訊架構](17_前端資訊架構.md) | ✅ v1.11（對講機雙手勢＋admin 7 頁 D-74 話題新聞頁） | 2026-07-25 |

狀態圖例：⬜ 未開始｜🟡 進行中／待議中｜✅ 定稿

> **2026-07-10 架構文檔深化**（設計＝[spec](../superpowers/specs/2026-07-10-架構文檔深化-design.md)、計畫＝[plan](../superpowers/plans/2026-07-10-架構文檔深化.md)）：逐子系統（7 群、8 輪）深潛重構後的程式碼，回填 05／09／10／12／17；共登記 58 項後端差距（A-1～A-58，六項 HIGH 見 [05 差距彙整](05_架構與設計.md#差距與重構項本文件貢獻給-16_wbs)）與 8 項前端差距（[12 §9](12_前端架構規範.md)）。**純文檔工作，未修改任何程式碼。**

## 寫作順序

02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 12 → 17 → 11 → 13 → 14 → 15 → 16（WBS 最後，收斂全部差距項）

## 與舊文件的關係

`docs/mvp/`、`docs/全庫人工決策盤點-待議.md` 為過時參考，全套定稿後移入 `docs/archive/`；其結論一律不直接繼承。
