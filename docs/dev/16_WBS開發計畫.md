# WBS 開發計畫（一次性重構）- 金孫 KinSun

> **版本:** v1.4 | **更新:** 2026-07-12 | **狀態:** 甲～己批全數完成；**新增庚批 56 工項**（2026-07-10 架構文檔深化發現，未排時程、待定優先序）
> **總工期**：2026-07-09 ～ 2026-08-20（6 週，✅ D-04 硬里程碑倒排）
> **施工順序**：甲→乙→丙→丁→戊→己（✅ Leo 核准 2026-07-08）；**分工：全批由 Leo 一人施工**（✅ 會-16，2026-07-09）。
> 每個工項出處文件都有細節；規模：S＝半天內、M＝1–3 天、L＝3 天以上。

---

## 甲、安全網與資料保全（P0 先行，目標 7/09–7/16）

| # | 工項 | 依據 | 規模 |
| :--- | :--- | :--- | :---: |
| 甲-1 | ✅ 完成（2026-07-09，D-63 修訂為輕量版）：一鍵手動備份 `scripts/backup_db.sh`＋首次備份實測；排程／輪替／演練取消 | D-63（DEP-1） | S |
| 甲-2 | ✅ 完成（2026-07-09）：音檔私有 bucket＋簽章 URL（效期 env 化預設 1 天）；已實測簽章 200／公開 400 | D-55（S-1） | M |
| 甲-3 | ✅ 完成（2026-07-09）：登入／註冊／裝置綁定 per-IP 節流（10 次／5 分鐘，env 可調） | D-58（S-2） | S |
| 甲-4 | ✅ 完成（2026-07-09）：文字訊息預設走完整管線（危急偵測＋回覆＋記憶）；旗標轉維運逃生口 | D-11（G-2） | S |
| 甲-5 | ✅ 完成（2026-07-09）：L1 保守留痕＋admin 告警橫幅；LINE 推播告警經 D-66 修訂取消 | D-31＋D-66（M-1、DEP-2） | M |
| 甲-6 | ✅ 完成（2026-07-09）：App 出站 adapter＋通知儲存＋家屬通知頁與未讀 badge；家屬 App 綁定補建＋存量回填（長輩側顯示待階段 5） | D-12（G-1、F-6） | L |
| 甲-7 | ✅ 完成（2026-07-09）：測試庫隔離（`KINSUN_TEST_DATABASE_URL`＋防呆＋session 清理＋Docker 本機庫配方） | D-69 | S |

## 乙、API 大改版（破壞性一次到位，目標 7/17–7/25）

| # | 工項 | 依據 | 規模 |
| :--- | :--- | :--- | :---: |
| 乙-1 | ✅ 完成（2026-07-09）：/api/v1 全端點＋統一信封＋路徑改名（前端已隨乙-5 同步） | D-23／D-27（API-1） | L |
| 乙-2 | ✅ 完成（2026-07-09）：標準錯誤碼＋繁中訊息表＋validation_error 統一（含 admin_disabled 中性措辭） | D-24（API-2） | M |
| 乙-3 | ✅ 完成（2026-07-09）：登出撤銷＋長輩裝置作廢重綁（回新綁定碼）；不做效期與 `expires_at`（D-25 修訂）；長輩帳密端點隨己-6 | D-25／D-71 | M |
| 乙-4 | ✅ 完成（2026-07-09）：routers/ 十檔＋prefix 上移＋tags＋刪死碼＋`GET /v1/elders` 改名（隨乙-1 落地） | D-28（API-5） | M |
| 乙-5 | ✅ 完成（2026-07-09）：`shared/` 共用包（信封／型別／字典／格式化）＋三端 /v1 與解包遷移＋admin 回翻 UI；D-50 各端剩餘字串常數化延至丁批 | D-46／50／51（F-2） | L |
| 乙-6 | ✅ 完成（2026-07-09）：admin messages `before` 回翻＋信封 meta（前端接上隨乙-5） | D-29（API-6） | S |
| 乙-7 | ✅ 完成（2026-07-09）：對講機上限 env 化＋DGX 兩服務請求驗證與上限＋503 標準化 | D-26（API-4） | S |

## 丙、架構與模組整理（行為不變的結構修，目標 7/26–8/01）

| # | 工項 | 依據 | 規模 |
| :--- | :--- | :--- | :---: |
| 丙-1 | ✅ 完成（2026-07-09）：TextSender 插座反轉，safety 對 channels 依賴歸零 | D-18（A-1） | S |
| 丙-2 | ✅ 完成（2026-07-09）：旁路模式也解析 elder_id，切旗標不再換記憶主鍵 | D-19（A-2） | S |
| 丙-3 | ✅ 完成（2026-07-09）：uvicorn --workers（WEB_WORKERS 預設 2）＋假設盤點＋池評估（15 連線）；雙 worker 實測 | D-20（A-3） | M |
| 丙-4 | ✅ 完成（2026-07-09）：elder_id 口徑＋真庫回歸；PgVectorStore 首個真庫測試；順修 pg 觀測測試的 D-69 漏網 | D-34（M-3） | S |
| 丙-5 | ✅ 完成（2026-07-09）：建構子預設對齊 config 200 | D-35（M-4） | S |
| 丙-6 | ✅ 完成（2026-07-09）：SAFETY_CONFIDENCE_HIGH/MID env 化；降級規則仍隨己-4 重設計 | D-41（M-6） | S |
| 丙-7 | ✅ 完成（2026-07-09）：risk_notification_logs 三件套＋notifier 留痕插座 | D-36（M-2） | S |
| 丙-8 | ✅ 完成（2026-07-09）：留存記憶帶【主動關懷｜intent】標記 | D-39（M-7） | S |
| 丙-9 | ✅ 完成（2026-07-09）：HSTS／nosniff／frame／Referrer＋CSP 全站 | D-57（S-3） | S |
| 丙-10 | ✅ 完成（2026-07-09）：X-Api-Key（未設＝內網不驗）＋requirements 鎖版（TTS 精確版待環境重建回填） | D-56（S-4） | S |
| 丙-11 | ✅ 完成（2026-07-09）：假雜湊補時間差＋email pattern＋turns 僅收 audio/*（415） | D-60／D-61（S-5、S-6） | S |
| 丙-12 | ✅ 完成（2026-07-09）：九檔 git mv 改名；web 面聚合測試檔維持現名（非 1:1，另議） | D-44 | S |
| 丙-13 | ✅ 完成（2026-07-09）：主 API /healthz＋mem0 稽核檔固定 data/mem0/ | D-67／D-65（DEP-3、DEP-4） | S |
| 丙-14 | ✅ 完成（2026-07-09）：AGENTS.md 白名單補 RAG ingest 直讀鍵 | D-70 | S |

## 丁、體驗與檢索強化（目標 8/02–8/08）

| # | 工項 | 依據 | 規模 |
| :--- | :--- | :--- | :---: |
| 丁-1 | ✅ 完成（2026-07-09）：SessionProvider（Context）＋七畫面全遷 useSession | D-45（F-1) | M |
| 丁-2 | ✅ 完成（2026-07-09）：觸覺＋提示音（自產資產）＋字級縮放上限管理；體感待實機驗收 | D-48（F-3） | M |
| 丁-3 | ✅ 完成（2026-07-09）：複製鈕＋QR 顯示＋長輩掃碼即綁；相機流程待實機驗收 | D-54（F-5） | M |
| 丁-4 | ✅ 完成（2026-07-09）：LLM reranker（gemini）＋explain；provider 選擇待 Leo 快速確認可否決 | D-40（M-5） | M |
| 丁-5 | ✅ 完成（2026-07-09）：GEMINI_MODEL_SAFETY／SUMMARY 按用途覆寫 | D-16（A-5） | S |
| 丁-6 | ✅ 完成（2026-07-09）：splash／adaptiveIcon 統一品牌暖米底 | D-68 | S |
| 丁-7 | ✅ 完成（2026-07-09）：401 即切回金鑰輸入頁 | D-52（F-4） | S |

## 戊、品質基建（與丁並行，目標 8/04–8/12）

| # | 工項 | 依據 | 規模 |
| :--- | :--- | :--- | :---: |
| 戊-1 | ✅ 完成（2026-07-10）：CI 五 job——pytest＋ruff／Pg 合約測試（pgvector service container）／frontend tsc＋建置／app tsc／pip＋npm audit（警示不擋門） | A-6 | M |
| 戊-2 | ✅ 完成（2026-07-10）：Gemini usage 落庫 llm_calls（收集器彙總工具迴圈）＋replies.round_trip_ms 端到端往返＋overview 各階段 p50／p95 與往返統計（admin 前端同步顯示） | D-05（A-7、G-6） | M |
| 戊-3 | ✅ 完成（2026-07-10）：worker 接線 100%＋app.py 組裝根 97%＋LineApiMessenger 100%＋rag 支援四模組 100%；pytest-cov 上 CI（--cov-fail-under=80，現況 87%） | M-8 | M |
| 戊-4 | ✅ 完成（2026-07-10）：標注集草案 60 句（含轉述／否定／比喻等困難負例，實測期修訂）＋`safety/evaluation.py` P/R 量測 CLI（詞表離線模式＋完整偵測器模式；漏報清單顯式列出） | D-05 | M |

## 己、會議決議回填批（✅ 2026-07-09 決議回填完成，穿插各批或殿後施工）

| # | 工項 | 依據 | 規模 |
| :--- | :--- | :--- | :---: |
| 己-1 | ✅ 完成（2026-07-10）：兩提醒 job 卸下同意檢查（照發；查無此長輩才略過）；ConsentGate 維持 | D-30（會-1） | S |
| 己-2 | ✅ 完成（2026-07-10，文案 Leo 核可）：LINE 綁定確認＋App 代辦同意文字；CONSENT_VERSION 2.0 | D-14／15／59＋D-62（會-3） | S |
| 己-3 | ✅ 完成（2026-07-10）：daily-summaries 端點（守門＋limit）＋App 長輩詳情「每日摘要」區塊＋shared 型別 | D-09（會-4） | M |
| 己-4 | ✅ 完成（2026-07-10）：三級制落地——絕對詞直判 L2、單一降級門檻（HIGH 移除）、prompt 改 0–2、119 提示掛 absolute 訊號、舊資料夾回、三端與文件標注集同步 | D-72＋D-10（會-5） | M |
| 己-5 | ✅ 完成（2026-07-10）：摘要提示納入摘要日 L1 理由（排除 L2 與 fail-safe 留痕）；worker 接 PgRiskEventStore | D-10（會-5） | S |
| 己-6 | ✅ 完成（2026-07-10）：帳號＝手機號碼（Leo 拍板）；首次掃碼配對＋帳密只管重登（未配對 403）；PUT /elders/{id}/account 代辦＋POST /elder-sessions（節流）＋App 兩端 UI＋elder_accounts 新表 | D-71 | L |
| 己-7 | 衛教資料遷移：自負責組員的 Supabase 取得資料 → 本專案 Supabase 入庫＋回答品質驗收 | D-03（會-14） | M |
| 己-8 | ✅ 完成（2026-07-10，範圍 Leo 核可）：revoke_consent 刪除；can_view_transcript 方法＋欄位全刪（冪等 DROP）；escalation_order 保留（家屬排序仍用） | D-13／09／10 | S |

無需工項的決議：會-6 詞表（實測時滾動加）、會-7 門檻數值（實測再調）、會-11 問候維持文字、會-15 麥克風文案照現值；會-8／9／10／13 擱置、會-12 掛起。

## 庚、架構文檔深化發現修復批（2026-07-10 深潛新增，未排入時程；待 Leo 定優先序）

> 來源：[2026-07-10 架構文檔深化](../superpowers/specs/2026-07-10-架構文檔深化-design.md)——七群逐模組深潛，登記 58 項後端差距（[05 差距表](05_架構與設計.md#差距與重構項本文件貢獻給-16_wbs)的 A-8～A-58）與 8 項前端差距（[12 §9](12_前端架構規範.md) 的 F-8～F-15）。**全部只記錄未動代碼**。下表把每項開成工項並標「問題編號（A-xx／F-xx）」以對應 05／12 細節。批內順序＝建議施工序（HIGH 先）。

### 庚1 立即修（HIGH，9 項）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-01 | ✅ 完成（2026-07-12，TDD）：pipeline 落庫門檻放寬至 ≥L1（通知維持 ≥L2），D-10 己-5「L1 小訊號進每日摘要」生產路徑生效；契約測試改寫＋全套 591 綠。已知副作用：健康報告出現「關注」級事件（本無 tier 過濾，接受；不想顯示另開工項） | A-39 | M |
| 庚-02 | 危急通知失敗可觀測：L2 通知 `delivered=False` 時重試／落死信／或 admin 告警（現 admin 只看分級器故障）。**家屬漏收警報＝最嚴重產品失敗卻無感知**。 | A-40 | M |
| 庚-03 | ⏸ **擱置（Leo 2026-07-12：著作權相關先不處理）**——RAG 來源著作權把關：`SourceValidator` 補查 `copyright_status`，或撤 `ntuh_epaper`／`cgmh`（DISALLOWED）的 `approved_for_rag`。 | A-26 | S |
| 庚-04 | ✅ 完成（2026-07-12，TDD）：`bind_elder_device` redeem 前驗 `invite.role is ELDER`，家屬邀請碼回 409 `invite_wrong_role`（未消耗碼、未發 token）；06 端點表＋錯誤碼表同步 | A-46 | S |
| 庚-05 | ✅ 完成（2026-07-12，TDD）：`DELETE /api/v1/sessions/all`＋`AccountService.logout_all_devices`（撤該家屬全部 token），與長輩 `revoke_elder_device` 對稱；06 端點表同步 | A-47 | S |
| 庚-06 | 記憶整理漏天修復：worker 停機跨多日重啟時，`run_consolidation` 改吃「上次整理→now」日範圍迴圈補整理（現只抓 previous_day、補跑一次→中間天數 turns 永不進長期記憶）。**唯一永久資料遺失風險**。 | A-18 | M |
| 庚-07 | 觀測五表欄位正名：`line_user_id` → `external_id`＋`channel`（現承載所有通道識別碼，違反 AGENTS.md「line_user_id 永不混用」鐵律）；含 schema 遷移＋pipeline／observability 寫入點。 | A-8 | M |
| 庚-08 | 多 worker 節流前置（D-20 相依）：`ratelimit` 改跨進程（DB／Redis）或明訂「多 worker 上線前不生效」；現 per-process，上線後上限×worker 數，長輩低熵手機號帳號與家屬同池同參，暴力破解面放大。 | A-54 | M |
| 庚-09 | 衛教升級旗標決策：`should_escalate_to_risk_engine` 接上確定性程式碼觸發 RiskDetector，或明文降級為 advisory（現唯一消費者是 agent prompt 文字，靠 LLM 自律）。緩解：pipeline 真風險引擎在 agent 前已獨立評估。 | A-27 | S |

### 庚2 正確性與可靠性（MEDIUM）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-10 | 危急分級 LLM 納入觀測：`RiskDetector.assess` 的 Gemini 呼叫移進 `collect_llm_usage` 範圍並補 trace row（現系統性漏計 token、安全模型延遲不可觀測——即 A-7 的殘缺項）。 | A-9 | S |
| 庚-11 | 錯誤路徑語音化：pipeline 級 fallback 與 TTS 降級改走 TTS 或 App 端語音提示（現純文字，語音優先長輩「有字無聲」）。 | A-10 | M |
| 庚-12 | 免除閘門重複解析：App 回合把 `turns.py` 已解析的 elder_id 傳入 `dispatch`，省掉 `inbound.py` 內第二趟 DB 查詢。 | A-11 | S |
| 庚-13 | consolidation 冪等：加「(elder_id, 日) 已整理」標記，避免同日重跑重覆 `mem0.add`（可併庚-06 一起做）。 | A-19 | S |
| 庚-14 | 回診提醒紀錄對齊：`appointments/jobs.py` 比照用藥 job 加 `sent==0` 守門（現無條件記錄→家屬健康報告顯示長輩實際沒收到的提醒）。 | A-34 | S |
| 庚-15 | 回診時間粒度：`Appointment` 加時刻欄位（現只有日期、實際時刻藏在 label 自由文字，無法做「前 N 小時」精準提醒）。 | A-35 | M |
| 庚-16 | 送達語意精確化：`delivered` 對 App 通道區分「落庫待拉取」與「真送達」（現 App 落庫即記 True，稀釋 D-36 可信度）。 | A-41 | S |
| 庚-17 | scheduler 單例保護：加 leader election／advisory lock（現無鎖，誤起雙 worker 重複提醒；與庚-08 多 worker 同源）。 | A-42 | M |
| 庚-18 | 交易包裹三處：`revoke_elder_device`、`login_elder`／`login_guardian` 的補綁定＋發 token 包進 `transaction()`（現部分失敗留半完成狀態；並補 Fake transaction 使合約測試涵蓋）。 | A-48 | S |
| 庚-19 | 邀請碼並發防護：redeem 加 `SELECT FOR UPDATE` 列鎖（現 TOCTOU，並發同碼可重複綁定）。 | A-49 | S |

### 庚3 安全與檢索強化（MEDIUM）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-20 | 憑證強度：scrypt N 調至 OWASP 2024 建議（參數隨值存可漸進升級）＋密碼複雜度移至服務層驗證；長輩帳號低熵手機號需搭配庚-08 節流。 | A-50 | S |
| 庚-21 | RAG embedding 鍵統一：線上 `LONGTERM_EMBEDDING_MODEL` 與離線 `EMBEDDING_MODEL` 收斂為單一鍵，並補列 `.env.example`（現只改其一會導致查詢與文件向量空間錯配）。 | A-28 | S |
| 庚-22 | RAG 檢索優雅降級：`embed_query` 失敗時退化（keyword 路獨立或退空結果不中斷），線上 embedder 加重試——對齊 Mem0 檢索的 fail-open 哲學。 | A-29 | S |
| 庚-23 | RAG seed 路徑補閘：seed ingest 也過 `SourceValidator`（現完全略過，`--source` 指定未核准來源時 seed 內容直接入庫）。 | A-30 | S |
| 庚-24 | DGX 服務端測試：`services/asr`／`services/tts` 補請求驗證／金鑰／併發閘的離線測試（現零測試；模型推論需 GPU 但這些是純邏輯）。 | A-13 | M |
| 庚-25 | 錯誤碼中央化：codes 收進 enum／常數，並同步 06 §3 錯誤碼表（現散落字串字面值，拼字錯靜默 fallback；表已脫節）。 | A-56 | S |
| 庚-26 | 連線池總量評估：對 Supabase 連線上限把關（N worker×5＋worker，庚-08 前置）。 | A-55 | S |

### 庚4 前端（MEDIUM／LOW）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-27 | admin 危急等級走共用字典：三頁改用 `shared/terms.tierLabel`（現硬編 `L{tier}`，維運看「L2」、家屬看「需留意」不一致）。 | F-10 | S |
| 庚-28 | 家屬端 token 過期流：401 自動清 session 回登入（現僅 `elder/talk` 處理 403，家屬端只顯示錯誤文字，12 §7 所述 `token_expired` 流未落地）。 | F-11 | M |
| 庚-29 | `POST /elders` payload 統一：App `{name}` 與 LIFF `{name, guardian_name}` 收斂契約（現後端須容忍兩形狀）。 | F-9 | S |
| 庚-30 | 三端 fetch wrapper 收斂進共用包（現信封／ApiError 已共用，client wrapper 各寫一份；模組解析雙軌 metro／vite）。 | F-12 | M |
| 庚-31 | 字串常數集中（D-50 未落地）：UI 文案含長輩端錯誤對照移出 inline 進共用字串檔。 | F-15 | M |
| 庚-32 | 前端無障礙細節：`Button` 一般尺寸提到 48pt（現約 46pt）；查證 `SafeAreaProvider` 掛載。 | F-14 | S |
| 庚-33 | 前端命名／冗餘清理：AuthProvider↔SessionProvider 對齊；`elder/talk` 冗餘 token state；LIFF `HealthReportPage` 重複型別；`TurnReply.duration_ms` 零消費。 | F-13 | S |

### 庚5 清理與命名（LOW，可批次順手）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-34 | RAG 死碼死表清理：`InMemoryVectorStore`（零引用）、`rag_crawl_jobs`（無寫入者）、`document_loader.py`（生產未接線）。 | A-31 | S |
| 庚-35 | 工具迴圈末輪修復：`agent.py` 第 `max_tool_iters` 輪的工具結果應回傳模型消化（現直接回 fallback，工具成功卻回退）。 | A-14 | S |
| 庚-36 | 例外命名：自訂 `MemoryError` → `MemoryStoreError`（遮蔽 Python 內建）。 | A-15 | S |
| 庚-37 | 群 1 小項三件：`text_input_enabled` 預設值統一；`VoiceReplyDelivery` docstring 去「LINE」；`FALLBACK_PROMPT`／`FALLBACK_REPLY` 合併。 | A-16 | S |
| 庚-38 | 記憶群小項：provenance 三值僅 self_claimed 流動（另兩值決定移除或接線）；`health_top_k` 接 settings；`LongTermStore.search` 簽章預設值對齊。 | A-22 | S |
| 庚-39 | RAG 小項四件：`ingestion.py:143` 冗餘 except；citation 對位；稽核補 document_id／url。 | A-33 | S |
| 庚-40 | 健康領域小項：`health-report` window_days 開放 query 參數；reminder kind 集中列舉。 | A-36 | S |
| 庚-41 | 安全群小項五件：症狀詞＋LLM 故障時 reason 誤導；proactive 參數名 `line_user_id`；evaluation docstring L3 殘留；deliveries.py 補進 AGENTS.md D-42 例外清單；risk_events.line_user_id 死欄。 | A-44 | S |
| 庚-42 | 帳號群小項五件：死碼 `get_elder_guardian`；長輩自助登出端點；`bind_elder_device` 重複讀 invite；store 註解滯後 DDL；AGENTS.md:76 布林命名範例對齊。 | A-52 | S |
| 庚-43 | 底座小項五件：`.env.example:70` 門檻註解去舊四級；`ERROR_MESSAGES["overloaded"]` 死碼；`web/envelope.py` 補單元測試；`Executor` Protocol 補 `transaction()`；`.env.example` 標「app 不讀」鍵。 | A-58 | S |
| 庚-44 | 兩組裝根重複接線：`PgRiskEventStore`／`PgConversationSummaryStore` 收進 Core（現兩根各 new，邊界與 traces 不一致）。 | A-57 | S |
| 庚-45 | 死欄與殘留清理：`turns`／`conversation_summaries`／`risk_events` 的 `line_user_id` 收縮；`__pycache__` 改名前 .pyc；recency 設計文件過時註記。 | A-25、A-37 | S |
| 庚-46 | 命名例外載明：短期記憶三件套住 `shortterm.py`（A-23）、RAG 持久層非三件套（A-32）、`FakeLongTermStore` 位置與測試替身命名（A-24）——載明為刻意例外或收斂。 | A-23／A-24／A-32 | S |

### 庚6 需 Leo 決策（非純工項）

| # | 事項 | 問題 |
| :--- | :--- | :---: |
| 庚-47 | keywords 詞表定稿：現為 placeholder（絕對 6＋症狀 5 詞），召回率受限——依會-6「實測滾動加」，需照護專業投入。 | A-43 |
| 庚-48 | 凌晨盲窗（00:00–03:00 昨日對話暫時檢索不到）：接受現況或調整整理時點——影響低但語意可見。 | A-21 |
| 庚-49 | 同意撤回：D-13 決議不做入口，`revoked_at` 為休眠欄位——確認維持，並注意 `login_elder` 以 `has_valid_consent` 代理「已配對」的語意副作用（未來若補撤回會誤擋登入）。 | A-51 |

### 庚7 範圍外文檔更正（非 05／09／10／12／17，深潛只登記未改）

| # | 文檔 | 需更正 |
| :--- | :--- | :--- |
| 庚-50 | CONTEXT.md | §52「長輩不設帳密」已被己-6 推翻（`elder_accounts` 存在）、缺 ElderAccount 詞條；§94 危急分級仍寫「L0–L3 四級」（D-72 已三級）（A-45／A-53） |
| 庚-51 | 06 API 設計規範 | §3 錯誤碼表補 `phone_taken`／`invalid_phone`／`not_paired`／`too_many_requests`／`unsupported_media_type`；`consent_revoked` 標「僅資料層預留」；`token_expired` 因 D-25 作廢（A-53／A-56） |
| 庚-52 | 07 模組規格與測試 | 「rag 8 檔」過期（實際 17 模組，A-33） |
| 庚-53 | 08 專案結構指南 | §4「service.py 建構子注入 store＋clock」與現實不符（實為 store＋new_id，A-38） |
| 庚-54 | 04_adr/ADR-003 | reranker 描述過時（現 rerank=True＋預設啟用）；provenance 描述不完整（inferred 也無寫入路徑）（A-20） |
| 庚-55 | 13 安全與就緒檢查 | §43「告警：無」應改「僅被動 admin 橫幅」；scrypt N=16384 標 ✅ 未註低於 OWASP 2024（A-45／A-50） |
| 庚-56 | 群 1／群 4 文檔清理 | CONTEXT.md turns 路徑；13 檢查表與 evaluation KPI 未交叉引用；notifications router 無專屬測試（A-17／A-45） |

**已於深化過程解決、無需工項**：A-12（`tools/health_rag.py` 無測試——實為誤判，handler 測試已存在於 `tests/rag/test_service_and_tool.py`，真缺口併入庚-09）；F-8（17 §3 全景圖補第 10 頁——階段 F 已完成）。

**覆蓋核對**：庚-01～庚-56 完整覆蓋 A-8～A-58（51 項）＋F-9～F-15（7 項）；A-1～A-7 為深化前既有差距，除 A-7（KPI 基建，戊-2 已完成、殘缺併庚-10）外皆已由丙批完成。

### 庚批統計

| 分區 | 項數 | 性質 |
| :--- | :---: | :--- |
| 庚1 立即修（HIGH） | 9 | 功能失效 2、安全 3、資料遺失 1、合規 1、命名鐵律 1、擴展前置 1 |
| 庚2 正確性與可靠性 | 10 | MEDIUM |
| 庚3 安全與檢索強化 | 7 | MEDIUM |
| 庚4 前端 | 7 | MEDIUM／LOW |
| 庚5 清理與命名 | 13 | LOW（可批次順手） |
| 庚6 需 Leo 決策 | 3 | 非純工項 |
| 庚7 範圍外文檔更正 | 7 | 純文檔 |
| **合計** | **56** | 規模粗估：M×11、S×42、決策×3 |

## 持續追蹤（非本 repo 施工）

- 台語 TTS 微調（另專案：語料清洗中→CosyVoice 3 vs VoxCPM2 對比，✅ D-01）——8 月初需對比結論以趕上發表。
- 8/11–8/19：實測驗收（KPI，數值屆時定——會-10）＋發表備援與彩排（會-13 延後至發表文件期一起定）＋README／CONTEXT 全面更新（G-7）＋CHANGELOG 起頭與 tag（15 §6）。
- 實測期並行：危急詞表滾動擴充（會-6）＋信心門檻校準（會-7）。
- 等待外部輸入：D-38 CAUTION（等組員回覆）。

## 里程碑

| 日期 | 檢查點 |
| :--- | :--- |
| 7/16 | 甲批完成：安全網補洞、備份上線　✅ **2026-07-09 提前完成**（甲-1～甲-7 全數） |
| 7/25 | 乙批完成：API v1 三端切換　✅ **2026-07-09 提前完成**（乙-1～乙-7 全數） |
| 8/01 | 丙批完成：結構修畢、全測試綠　✅ **2026-07-09 提前完成**（丙-1～丙-14 全數） |
| 8/08 | 丁批完成：體驗強化＋台語 TTS 對比結論　✅ **App 側 2026-07-09 提前完成**（台語 TTS 對比仍依另專案時程） |
| 8/12 | 戊批完成：CI 綠、KPI 可量測　✅ **2026-07-10 提前完成**（戊-1～戊-4 全數） |
| 8/13、8/18 | 彩排（暫定——會-13 延後，發表文件期確認） |
| **8/20** | **期末發表（硬里程碑）** |
| — | **庚批（56 項）未排入時程**——2026-07-10 架構深化新發現。建議至少在發表前完成庚1（9 項 HIGH）：其中庚-01（已拍板功能失效）、庚-02（危急通知漏收無感知）、庚-03（著作權合規）直接影響 demo 可信度與法遵，庚-04／庚-05 為安全邊界。餘批待 Leo 定優先序。 |

## 變更紀錄

| 版本 | 日期 | 變更 |
| :--- | :--- | :--- |
| v1.0 | 2026-07-08 | 初版：六批 40 工項＋里程碑；順序經 Leo 核准；分工待會-16 |
| v1.1 | 2026-07-09 | 會議決議回填：己批填入 8 個實際工項；分工＝Leo 單人（會-16）；乙-3／丁-3／丙-6 加 D-71／D-72 連動標註；彩排改暫定 |
| v1.2 | 2026-07-09 | D-71 三細節回填：乙-3 改 token 永久化（不做效期）；丁-3／己-6 解鎖 |
| v1.3 | 2026-07-10 | 戊批完工標記：CI 五 job＋覆蓋門檻 80%（現況 87%）、KPI 量測基建（token／往返 P50/P95／危急 P/R）全數落地 |
| v1.4 | 2026-07-12 | **新增庚批**：架構文檔深化（七群深潛）發現的 58 項後端＋8 項前端差距開成 56 個工項，分七區（立即修 HIGH 9／正確性 10／安全強化 7／前端 7／清理 13／待決策 3／範圍外文檔 7）；標註兩項深化中已解決（A-12 誤判、F-8 已補圖）。庚批未排入 8/20 時程，建議至少完成庚1 |
