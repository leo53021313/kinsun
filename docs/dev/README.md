# docs/dev — 開發文件（重規劃版）

> 依老師的 VibeCoding_Workflow_Templates（完整流程模式）重新規劃的全套開發文件。
> 設計依據：[docs/superpowers/specs/2026-07-07-docs-dev全套文件重規劃-design.md](../superpowers/specs/2026-07-07-docs-dev全套文件重規劃-design.md)。
> 內容基準：**as-is＋to-be 對照**；to-be 為一次性重構的契約。
> 鐵律：所有決策由 Leo／團隊拍板，AI 不代填；未拍板一律 ⚠ 待議，登記於 [00_決策清單.md](00_決策清單.md)。

## 文件狀態表

| # | 文件 | 狀態 | 最後更新 |
| :---: | :--- | :--- | :--- |
| 00 | [決策清單](00_決策清單.md) | ✅ D-01～D-77 全回填（D-77 附近地點搜尋六項核定、**八個工作項全完成**，人工真 LLM 驗證 18/18 全對並追加修復一個 `place` 距離護欄 Critical；D-76 統一排程十二項核定、**五刀全完成**；D-38 掛起、4 項擱置；D-74 消費端完成；D-75 濫用審核採納並重寫接法；旗標預設開但支撐數字同日作廢待重跑） | 2026-07-27 |
| — | [2026-07-08 會議決策議程](2026-07-08_會議決策議程.md) | ✅ 決議已回填（會議紀錄） | 2026-07-09 |
| 02 | [專案簡報與PRD](02_專案簡報與PRD.md) | ✅ v1.4（US-C1／C2 改寫為統一排程、新增 US-C3 長輩用說的建立提醒；KPI 數值⏸實測後定；US-B3 問候自適應註記） | 2026-07-17 |
| 03 | [BDD情境](03_BDD情境.md) | ✅ 定稿（D-72 三級制已落地） | 2026-07-09 |
| 04 | [ADR（04_adr/）](04_adr/README.md) | ✅ 定稿（11 筆；ADR-003 補述 庚-54） | 2026-07-13 |
| 05 | [架構與設計](05_架構與設計.md) | ✅ v1.54（延遲觀測細拆：§12 span 盤點補 memory_assemble 細拆段——shortterm_recent／gather_facts 七路／mem0_search_raw 逐路／mem0 內部三段（embed／向量查詢／rerank），純觀測，數據用途＝定 rerank 去留；回退話術改走預錄語音（V-02／A-10，庚-11 改判）：§8 錯誤路徑表由「❌ 純文字」改為「✅ 預錄語音」；一輪總預算 `TURN_BUDGET_SECONDS=30`（辛-21）：§8 錯誤路徑表與 NFR 實現；附近地點搜尋追加 2026-07-28 端到端驗證修復：`place` 距離護欄 50 公里＋回傳講出中心點地名；新增附近地點搜尋：`places` 資料表入 §4.1 獨立群組、tools 補 search_nearby_places（三條座標安全界線＋chiropractic 只收整復推拿）、web_search 職責收窄；Opik 觀測加定期重探，首探失敗不再是終身判決；回頭查核補完六項缺口；Container 表補 RAG 週更 Worker、排程宣告集中 cron/registry.py、scheduler/→cron/ 更名；Opik 全面開啟＋日誌內容政策定案；架構對比 ref/hermes-agent 後六項邊界補強：排程工具安全界線 4、語音後端白名單、危急通知投遞三修、logging_setup、情境組裝等待上限；（新增 turn_context.turn_sources 跨層 seam 與冒名防線、危急症狀詞翻案、連線層 keepalive；TTS 分段串流（App 限定）＋回覆字數 40→30；第二批：回合內併發——情境組裝與兩道安全檢查重疊、mem0 兩次檢索並行、Gemini 逾時修復；第一批：觀測落庫與提醒標記改走 background.run、事實提供者並行查，相鄰 A/B 端到端 16.91s→11.67s；統一排程 D-76 五刀全完成：schedules 取代 medications／appointments、提醒管線改寫為單一每分鐘派送；時間改每輪注入情境、get_current_time 移除；§8.5 補濫用審核：三類越權／位置在家屬通報之後為安全屬性／誤攔防線三層；§12 離線評測四實驗；D-74 消費端） | 2026-07-30 |
| 06 | [API設計規範](06_API設計規範.md) | ✅ v1.19（排程名稱 50 字、地名 100 字兩處上限；422 欄位明細不外洩 pydantic 原文與 regex；全空白名稱兩支同調；錯誤契約四修：框架層碼、排程碼、missing_token 統一、Elder 型別補 nickname；邊界輸入三修：bearer 大小寫、邀請碼空白、PUT kind 明確 400；位置座標補範圍驗證（V-04），REST 忽略而非 422；WS 位置訊框補型別把關（V-03）；**新增 `POST/DELETE /api/v1/push-tokens`** 裝置推播 token 註冊（真推播 D-08 階段 5）；**新增 `GET /api/v1/elder-notifications`**：長輩讀自己的用藥／回診提醒與主動關懷——先前提醒落庫後誰都讀不到（X-01）；`GET /admin/jobs` 母體改全系統排程宣告＋`owner`／`can_run_now` 兩欄，手動觸發跨程序回 409 `job_not_runnable_here`；`GET /admin/jobs` 逾期偵測欄位＋`never_ran`＋**逾期容許量逐 job**；新增 GET /turns/chunks/{index} 分段語音串流＋三個錯誤碼，POST /turns 回應加 chunk_count／reply_digest；統一排程 /schedules 取代 /medications 與 /appointments；新增 `GET /api/v1/admin/news` 話題新聞檢視，D-74） | 2026-07-29 |
| 07 | [模組規格與測試](07_模組規格與測試.md) | ✅ v1.57（延遲觀測細拆：memory 三檔＋mem0_factory 補細粒度 span，純觀測零行為變更，總測試 2450；跨來源 URL 去重（同頁被多來源各收一份、佔 chunk 47%）；家屬 L2 通知文案改只引長輩原話（Leo 定案）：不轉述分級器 reason、不放「風險等級」字樣，`Notifier.notify` 加 `user_text`；回退話術預錄語音：AckAudioCache.standby_phrases／clip_for_text＋VoiceReplyDelivery.deliver_standby，總測試 2357；未註冊工具導致退化輸出修復：出站護欄＋提示詞／註冊表對帳 warning，+13 測試；`pipeline.py`／`llm.py` 補一輪總預算（辛-21，+13 測試）；連線超賣治本：CLI 小池＋池 5→3；RAG crawler 補 cookie jar（health99 先發 session cookie 再轉址回同址，無 cookie 判定無限轉址、84/85 頁全滅）；RAG text_cleaner 剝除點閱計數整行；附近地點搜尋 tools 列追加端到端驗證修復；RAG crawler 實戰修五瑕疵：WebForms、JSON 嗅探、垃圾連結、http 升級、URL 編碼＋NUL；工具回合補 thinking_config=MEDIUM；統一排程五刀全完成、舊模組退役） | 2026-07-30 |
| 08 | [專案結構指南](08_專案結構指南.md) | ✅ v1.21（locations/ 入目錄樹＋座標判準單一出處；ack_audio.py 兼供回退話術預錄音檔；新增附近地點搜尋：頂層 `places/`（models/geo/store/categories/refine/ingest）＋`tools/places.py`；scheduler/→cron/＋registry.py；transport_agent/ 移出 src/ 到 docs/archive/（仍在版控）、ruff 例外改掛封存區；接線三步改為「先宣告後綁定」；speech/ 補 chunking.py 回覆切句；頂層新增 background.py；schedules/ 八檔全配、medications/ 與 appointments/ 退役；頂層新增 clock.py、tools/clock.py 移除；news/fetchers 補 rss.py；admin 八頁 NewsPage） | 2026-07-29 |
| 09 | [模組依賴關係](09_模組依賴關係.md) | ✅ v1.12（新增附近地點搜尋：領域層補 places〔僅依賴 db〕、Protocol 47→48／合約 19→20；cron/registry 只依賴 config，新增 app.py／rag.worker 兩條向下邊，DAG 結論不變；基礎層新增 background，零領域依賴不新增循環；濫用審核走 LLMClient seam 不新增對外依賴） | 2026-07-28 |
| 10 | [類別關係](10_類別關係.md) | ✅ v1.24（新增附近地點搜尋：Protocol 總表新增 PlaceStore（47→48）；cron 群補 JobSpec 排程宣告；群 2 補 PreparedTurn 與 CareAgent.prepare，非 Protocol；FactProvider 並行呼叫但順序按注入索引；統一排程五刀全完成、舊模組類別移除；FactProvider 六段、TimeFacts 排首位；群 4 補 AbuseModerator／AbuseClassifier／ModerationResult，VoicePipeline 補選配 moderator） | 2026-07-27 |
| 11 | [審查與重構指南](11_審查與重構指南.md) | ✅ v1.1（CI 已落地；docs/dev 同步鐵律入自查） | 2026-07-17 |
| 12 | [前端架構規範](12_前端架構規範.md) | ✅ v1.7（admin 話題新聞頁 D-74；web 端 React 19.2.8＋react-router 8.3） | 2026-07-25 |
| 13 | [安全與就緒檢查](13_安全與就緒檢查.md) | ✅ v1.6（日誌脫敏結案：只記系統事實、內容進 Opik；新增工具寫入授權與語音後端誤設兩列；日誌脫敏需重驗；§G 補外呼逾時與 D-22 部分落地；位置隱私列；依賴掃描與 healthz 結案） | 2026-07-27 |
| 14 | [部署與運維](14_部署與運維.md) | ✅ v1.26（**§3.5 pool_size 15→25＋爆線症狀補「近滿載＝排隊變慢」**；**kinsun.sh 新增 update 指令**（僅 opik）；**Opik 啟動不再問 registry**：opik.sh 本地加 `--pull missing`，registry 瞬斷不再讓整組起不來，映像改明確手動升級；**新增裝置推播章節**：五個前置步驟、iOS 需付費 Apple 會員、推播沒響的判讀順序；**連線超賣已治本：池 5→3＋CLI 小池 2**；**§3.5 連線上限更正＝15 非 60**（DATABASE_URL 走 pooler session mode，預設 4 進程×5 已超賣）；RAG Runbook 補四則實戰前提：CLI 連線額度、免費層每日嵌入約 1,000 條／金鑰、評測撞配額會偽裝成品質問題、golden set 指定來源須與內容政策一致；Opik 觀測定期重探；排程器 systemd unit；排程停擺根因＝浮點等值比對；RAG 週更 hpa 憑證 bundle 與爬深 ≥100） | 2026-07-30 |
| 15 | [文檔與維護指南](15_文檔與維護指南.md) | ✅ v1.2（同步鐵律＋前端／WBS／排程宣告三列） | 2026-07-27 |
| 16 | [WBS開發計畫](16_WBS開發計畫.md) | ✅ v1.25（庚-11（A-10 有字無聲）由「不改」改判並完成——07-28 的安撫話快取讓成本由 M 降到 S，且「螢幕有字」對純語音長輩不成立；新增辛-22 修未註冊工具導致的退化輸出已完成（B 提示詞動態化留待辦）；新增辛-21 一輪總時間預算已完成；新增辛-20 修對講機改走 WS 後定位失效已完成；辛-19 非同步工具調用與併發對話已完成；新增辛-18 附近地點搜尋已完成；辛-17 工具回合思考層級已完成；辛-15 架構對比後六項邊界補強已完成、辛-16 第二批未施工）（辛-14 三項修復完成；辛-13 全流程模擬實測完成；辛-10 濫用審核＋辛-11 觀測與評測強化＋辛-12 防呆待施工；RAG 個人庫驗收；甲～庚結案＋辛批 12 項；⚠ 庚-09 待 Leo 確認） | 2026-07-29 |
| 17 | [前端資訊架構](17_前端資訊架構.md) | ✅ v1.13（**新增 /elder/notifications 長輩提醒頁＋對講機鈴鐺未讀 badge**（X-01）；對講機資料需求對齊 WS 長連線＋位置鍵名兩路徑一律 `location`；雙手勢＋admin 7 頁 D-74 話題新聞頁） | 2026-07-29 |

狀態圖例：⬜ 未開始｜🟡 進行中／待議中｜✅ 定稿

> **2026-07-10 架構文檔深化**（設計＝[spec](../superpowers/specs/2026-07-10-架構文檔深化-design.md)、計畫＝[plan](../superpowers/plans/2026-07-10-架構文檔深化.md)）：逐子系統（7 群、8 輪）深潛重構後的程式碼，回填 05／09／10／12／17；共登記 58 項後端差距（A-1～A-58，六項 HIGH 見 [05 差距彙整](05_架構與設計.md#差距與重構項本文件貢獻給-16_wbs)）與 8 項前端差距（[12 §9](12_前端架構規範.md)）。**純文檔工作，未修改任何程式碼。**

## 寫作順序

02 → 03 → 04 → 05 → 06 → 07 → 08 → 09 → 10 → 12 → 17 → 11 → 13 → 14 → 15 → 16（WBS 最後，收斂全部差距項）

## 與舊文件的關係

`docs/mvp/`、`docs/全庫人工決策盤點-待議.md` 為過時參考，全套定稿後移入 `docs/archive/`；其結論一律不直接繼承。
