# WBS 開發計畫（一次性重構）- 金孫 KinSun

> **版本:** v1.9 | **更新:** 2026-07-17 | **狀態:** 甲～庚批完成（庚批 2026-07-13 結案：50 完成＋擱置 RAG／著作權＋1 不改；⚠ 庚-09 無完成標記且程式未接線，實為 55/56——待 Leo 確認）；內測基礎建設（D-73）✅ 完工；辛批 9 項全數完成（辛-9 迄 2026-07-17） 
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
| 庚-02 | ✅ 完成（2026-07-12，TDD）：admin overview 新增 `guardian_notification_failure` 告警——近 60 分鐘任一筆 `delivered=False` 即紅字橫幅（門檻 1，不設噪音緩衝）；`RiskNotificationLogStore.count_failed_since` 三件套＋契約測試；OverviewPage 依 kind 分文字。採最小方案（Leo 拍板：不做重試／死信，發表期靠後台盯）。 | A-40 | M |
| 庚-03 | ⏸ **擱置（Leo 2026-07-12：著作權相關先不處理）**——RAG 來源著作權把關：`SourceValidator` 補查 `copyright_status`，或撤 `ntuh_epaper`／`cgmh`（DISALLOWED）的 `approved_for_rag`。 | A-26 | S |
| 庚-04 | ✅ 完成（2026-07-12，TDD）：`bind_elder_device` redeem 前驗 `invite.role is ELDER`，家屬邀請碼回 409 `invite_wrong_role`（未消耗碼、未發 token）；06 端點表＋錯誤碼表同步 | A-46 | S |
| 庚-05 | ✅ 完成（2026-07-12，TDD）：`DELETE /api/v1/sessions/all`＋`AccountService.logout_all_devices`（撤該家屬全部 token），與長輩 `revoke_elder_device` 對稱；06 端點表同步 | A-47 | S |
| 庚-06 | ✅ 完成（2026-07-12，TDD，含庚-13）：`run_consolidation` 改吃 `(short_term, long_term, log, now)`——掃「上次整理日之後～今日之前」每個有對話的完整日，逐日 `list_for_range` 補整理；停機跨多日重啟不再漏天。新增 `MemoryStore.list_for_range`／`day_starts_with_turns`（Pg＋Fake）。worker／CLI 皆已接線。全套 627 綠。 | A-18 | M |
| 庚-07 | ✅ 完成（2026-07-12）：觀測五表（webhook_events／asr_calls／llm_calls／tts_calls／replies）`line_user_id` → `external_id`＋新增 `channel`，正名兼消除「line_user_id 混用」鐵律違反。含冪等 schema 遷移（DO 區塊守門 RENAME＋`ADD COLUMN IF NOT EXISTS channel`，新舊庫皆適用）、models／store（含 Fake）三件套、pipeline 全鏈 threading、邊界（inbound dispatch 取 `msg.channel.value`、LINE webhook 記 `channel="line"`）、admin `_trace_json` 回傳改 `external_id`＋`channel`、前端 TraceDetail 型別與頁面同步。`channel` 於 record 端預設 `""`（對齊 DB 欄預設）。契約測試補 channel round-trip、dispatch 測試證通道貫穿。全套 628 綠。 | A-8 | M |
| 庚-08 | ✅ 完成（2026-07-12，跨進程方案）：新增 `PgRateLimiter`（Postgres 共享滑動視窗，per-key `pg_advisory_xact_lock` 串行「清舊→計數→寫入」精確計數、掛鐘可跨進程、fail-open）＋`rate_limit_hits` 表；抽 `RateLimiter` Protocol，app.py 正式組裝改注入 Pg 版（記憶體版留測試／單 worker fallback）。多 worker 上限不再×worker 數。Pg IT 測試鎖「兩實例共用計數」。沿用既有 `AUTH_RATE_LIMIT_*`，無新增 env。 | A-54 | M |
| 庚-09 | 衛教升級旗標決策：`should_escalate_to_risk_engine` 接上確定性程式碼觸發 RiskDetector，或明文降級為 advisory（現唯一消費者是 agent prompt 文字，靠 LLM 自律）。緩解：pipeline 真風險引擎在 agent 前已獨立評估。⚠ **2026-07-17 對齊檢查**：本項無完成標記且程式仍未接線——與表頭「56 項全數結案」不符（實為 55/56），待 Leo 確認是漏標還是漏做 | A-27 | S |

### 庚2 正確性與可靠性（MEDIUM）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-10 | ✅ 完成（2026-07-12，TDD）：pipeline 新增 `_assess`——分級呼叫包進 token 收集器並補記 llm_call trace（model_name＝`GEMINI_MODEL_SAFETY`、fail-safe 以 `llm:error` 訊號記 error）。每輪 llm_calls 1→2 筆，分級 token 與生成筆分離（測試鎖定）。 | A-9 | S |
| 庚-11 | ⏸ **不改（Leo 2026-07-12：現狀可接受）**——錯誤情境頻率低、螢幕有字；曾評估 expo-speech 裝置語音與預錄提示音兩案。 | A-10 | M |
| 庚-12 | ✅ 完成（2026-07-12，TDD）：`dispatch` 加可選 `elder_id`，App turns 傳入已解析結果即跳過重查；LINE 路徑照舊。每輪省一趟 DGX→Supabase 往返。 | A-11 | S |
| 庚-13 | ✅ 完成（2026-07-12，TDD，隨庚-06）：新增 `memory_consolidations` 表（PK `(elder_id, day)`）＋`ConsolidationLogStore` 三件套（`record` 用 `ON CONFLICT DO NOTHING`）；`run_consolidation` 跳過已標記日 → 同日重跑（含 admin 手動觸發）不重覆 `mem0.add`。合約測試 Fake＋Pg。 | A-19 | S |
| 庚-14 | ✅ 完成（2026-07-12，TDD）：回診 job 接住長輩送達數，0 即不記 reminder_logs（家屬通知照發、可口頭轉告）。 | A-34 | S |
| 庚-15 | ✅ 完成（2026-07-12，TDD，Leo 選「時刻入欄＋提醒帶時間」層級）：`Appointment.time`（選填 HH:MM）全鏈——DDL 冪等遷移、store／service／API（`invalid_time` 400）、提醒訊息帶時間（「今天 10:30 要回診囉」）、App 表單時間選擇器＋LIFF `type=time`＋admin 顯示、shared 型別。「前 N 小時」排程另議。 | A-35 | M |
| 庚-16 | ✅ 完成（2026-07-12，TDD，誠實標註方案）：`ChannelRouter.send_text_channels` 回傳成功通道名；`risk_notification_logs` 加 `channels` 欄；admin 危急通知頁對僅走 App 的成功顯示「已入通知匣（待開啟）」。真送達（讀取回條）留待階段 5 推播。 | A-41 | S |
| 庚-17 | ✅ 完成（2026-07-12，TDD）：`ScheduleStateStore.try_claim` 條件式 UPDATE 原子先搶先贏——執行前搶占，輸家跳過；不持長 DB 鎖。交錯競態測試＋合約測試（Fake＋Pg）。 | A-42 | M |
| 庚-18 | ✅ 完成（2026-07-12，TDD）：三處包 `transaction()`（store 補 tx 參數）；`FakeAccountStore.transaction` 改快照回滾與 Pg 對齊，原子性可離線驗證。 | A-48 | S |
| 庚-19 | ✅ 完成（2026-07-12，TDD）：`get_invite` 加 `for_update`，redeem 讀碼＋檢查＋寫入同交易列鎖；失敗計數 commit 後才拋（行為不變）。Pg IT 並發測試：兩執行緒同碼恰一成功。 | A-49 | S |

### 庚3 安全與檢索強化（MEDIUM）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-20 | ✅ 完成（2026-07-13，TDD）：PROD_SCRYPT_N=2**17（OWASP 2024）＋動態 maxmem，參數隨值存零遷移；`_validate_password` 下沉服務層（password_too_short）；測試環境 conftest 降 2**14 保速、生產參數專測把關。 | A-50 | S |
| 庚-21 | ⏸ **擱置（Leo 2026-07-12：RAG 相關先不處理）** | A-28 | S |
| 庚-22 | ⏸ **擱置（Leo 2026-07-12：RAG 相關先不處理）** | A-29 | S |
| 庚-23 | ⏸ **擱置（Leo 2026-07-12：RAG 相關先不處理）** | A-30 | S |
| 庚-24 | ✅ 完成（2026-07-13）：兩服務各補離線特性測試（金鑰 401、空/超大輸入、併發閘 503、healthz、TTS 回應契約 audio/mp4＋X-Duration-Ms）——假模型 monkeypatch，CI 無 GPU 可跑（12 測試）。 | A-13 | M |
| 庚-25 | ✅ 完成（2026-07-13）：`web/errors.py` ErrorCode（StrEnum，34 碼）唯一出處，web 層字面值全換；雙向完整性測試（每碼必有繁中文案／文案表無孤兒，overloaded 掛 _PENDING_REMOVAL 待庚-43）；06 §3 表同步（兼辦庚-51 表半邊）。 | A-56 | S |
| 庚-26 | ✅ 完成（2026-07-13）：DATABASE_POOL_MAX_SIZE（預設 5）入 config；總量公式（WEB_WORKERS×池＋排程×池 ≤ 直連 60、WEB_WORKERS 安全上限約 8、勿換 6543 交易池化埠）寫入 .env.example／kinsun.sh／14 §3.5。 | A-55 | S |

### 庚4 前端（MEDIUM／LOW）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-27 | ✅ 完成（2026-07-13，Leo 選並列格式）：shared/terms 加 adminTierLabel（「L2 需留意」——維運保留編號、詞彙對齊家屬端），admin 四頁換用。 | F-10 | S |
| 庚-28 | ✅ 完成（2026-07-13）：SessionProvider 加 useSignOutOnAuthError（401→signOut→守衛導回登入；登入／註冊頁不適用），家屬五畫面 catch 全接。token_expired 本身已因 D-25 作廢，本工項處理的是「撤銷」情境。 | F-11 | M |
| 庚-29 | ✅ 完成（2026-07-13，Leo 選統一）：LiffVerifier 改回傳 LineIdentity（sub＋name claim），家屬名由後端取 ID token 顯示名稱（比前端自送可信）；payload 三端統一 {name}，LIFF 移除 getProfile。 | F-9 | S |
| 庚-30 | ✅ 完成（2026-07-13，Leo 選現在做）：shared/client.ts createApiClient 工廠——共同流程一份，三端差異（App baseUrl＋Bearer／LIFF ID token／admin X-Admin-Key＋401 通知）設定注入；呼叫點簽章不變。 | F-12 | M |
| 庚-31 | ✅ 完成（2026-07-13，Leo 選全量）：三端各建 strings.ts（App 121 條含 3 動態函式／LIFF 40 條／admin 141 條含 13 動態），使用者可見文案全數集中、改文案只動字串檔；分隔標點與後端訊息刻意保留原地。D-50 就此落地。 | F-15 | M |
| 庚-32 | ✅ 完成（2026-07-13）：Button minHeight 48；SafeAreaProvider 查證＝expo-router ExpoRoot 內建、不需自掛（根 layout 註記）。 | F-14 | S |
| 庚-33 | ✅ 完成（2026-07-13）：12 文檔統一稱 SessionProvider；talk 冗餘 token state 移除；HealthReportPage 型別查證已於乙-5 共用化（結案註記）；duration_ms 註記保留給虛擬形象對嘴。 | F-13 | S |

### 庚5 清理與命名（LOW，可批次順手）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-34 | ✅ 完成（2026-07-13）：InMemoryVectorStore／document_loader.py（含測試）刪除；rag_crawl_jobs DROP TABLE 退役。 | A-31 | S |
| 庚-35 | ✅ 完成（2026-07-13，TDD）：迭代上限後補一次消化呼叫——工具結果送回模型產文字，仍要工具才回退。 | A-14 | S |
| 庚-36 | ✅ 完成（2026-07-13）：MemoryError → MemoryStoreError，不再遮蔽內建。 | A-15 | S |
| 庚-37 | ✅ 完成（2026-07-13）：webhook 預設對齊 True；docstring 通道中立；回退話術統一單一出處（agent.FALLBACK_REPLY）。 | A-16 | S |
| 庚-38 | ✅ 完成（2026-07-13）：LONGTERM_HEALTH_TOP_K 入 settings；Protocol 簽章對齊；provenance 依 D-37 載明。 | A-22 | S |
| 庚-39 | ✅ 完成（2026-07-13）：冗餘 except 收斂；citation 兩路徑對位（fallback [:2] 同源／LLM 全列重組）；稽核補 document_id／url。 | A-33 | S |
| 庚-40 | ✅ 完成（2026-07-13）：health-report ?window_days=1..90；REMINDER_KINDS 集中列舉、四寫入端換常數。 | A-36 | S |
| 庚-41 | ✅ 完成（2026-07-13，TDD）：症狀詞＋LLM 故障 reason 改「命中症狀詞」；proactive 參數正名；L3 殘留清；D-42 清單補 deliveries.py（第五件死欄併庚-45）。 | A-44 | S |
| 庚-42 | ✅ 完成（2026-07-13）：長輩自助登出（DELETE /sessions 開放長輩 token＋對講機頁登出鈕，Leo 拍板）；redeem 加 expect_role 免重讀；死碼 get_elder_guardian 刪；store 註解對齊；AGENTS.md 布林範例改 has_valid_consent。 | A-52 | S |
| 庚-43 | ✅ 完成（2026-07-13）：門檻註解三級制；overloaded 死碼刪；test_web_envelope 5 測試；Executor 補 transaction() 拔 type:ignore；RAG ingest 鍵標「app 不讀」。 | A-58 | S |
| 庚-44 | ✅ 完成（2026-07-13）：PgRiskEventStore／PgConversationSummaryStore 收進 Core，兩根接線單一出處。 | A-57 | S |
| 庚-45 | ✅ 完成（2026-07-13，Leo 核定 DROP）：三表 line_user_id 死欄收縮（冪等 DROP，序在回填後）；recency 設計文件過時註記；__pycache__ 殘留清理。 | A-25、A-37 | S |
| 庚-46 | ✅ 完成（2026-07-13，Leo 選載明）：AGENTS.md 例外清單補三條（shortterm.py／RAG 持久層／FakeLongTermStore）。 | A-23／A-24／A-32 | S |

### 庚6 需 Leo 決策（非純工項）

| # | 事項 | 問題 |
| :--- | :--- | :---: |
| 庚-47 | ✅ 完成（2026-07-13，Leo 拍板全數納入）：D-32 候選 35 詞全收（11→46 詞）；標注集評測 P 61.1→66.7%、R 40.7→51.9%、誤報持平——純提升。 | A-43 |
| 庚-48 | ✅ 完成（2026-07-13，Leo 選提前）：整理改 00:05（cron 5 0 * * *），凌晨盲窗 3 小時→5 分鐘；掛同鍵的清理 jobs 隨移離峰 0 時段。 | A-21 |
| 庚-49 | ✅ 完成（2026-07-13，Leo 選維持）：不做撤回；login_elder 註記「同意代理配對」語意地雷與未來改法。 | A-51 |

### 庚7 範圍外文檔更正（非 05／09／10／12／17，深潛只登記未改）

| # | 文檔 | 需更正 |
| :--- | :--- | :--- |
| 庚-50 | CONTEXT.md | ✅ 完成（2026-07-13）：己-6 長輩帳密＋D-72 三級＋turns 路徑更正 |
| 庚-51 | 06 API 設計規範 | ✅ 完成（2026-07-13，於庚-25 兼辦）：錯誤碼表全面同步（補 8 碼、token_expired 作廢、invalid_signature 移除） |
| 庚-52 | 07 模組規格與測試 | ✅ 完成（2026-07-13）：rag 16 模組（庚-34 退役後） |
| 庚-53 | 08 專案結構指南 | ✅ 完成（2026-07-13）：注入描述對齊 store＋new_id |
| 庚-54 | 04_adr/ADR-003 | ✅ 完成（2026-07-13）：reranker 丁-4 已啟用＋provenance 補述 |
| 庚-55 | 13 安全與就緒檢查 | ✅ 完成（2026-07-13）：告警兩則橫幅＋scrypt 2**17（庚-20） |
| 庚-56 | 群 1／群 4 文檔清理 | ✅ 完成（2026-07-13）：turns 路徑＋13 補 evaluation KPI 交叉引用；notifications router 測試查證已有（test_api_app_auth 三測試） |

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

## 辛、發表前功能補強（2026-07-12 起，Leo 逐項指示追加）

| # | 工項 | 依據 | 規模 |
| :--- | :--- | :--- | :---: |
| 辛-1 | ✅ 完成（2026-07-12）：App 家屬端用藥／回診管理頁（新增／編輯／刪除；詳情頁轉目錄＋管理入口＋focus 重載；新依賴 datetimepicker）——關閉 app/README「App 版編輯後續補」已知限制；後端零改動 | Leo 指示（spec：superpowers/specs/2026-07-12-app用藥回診編輯-design.md） | M |
| 辛-2 | ✅ 完成（2026-07-14）：agent 自我進化——每晚反思與策略記憶：strategies 領域（store 三件套＋反思解析「全有全無」＋濾網逐條丟＋facts 注入 system prompt）＋夜間批次第三步＋admin 守則檢視／撤銷（條件式 UPDATE 回報命中）＋`REFLECTION_` 四鍵；反思訊號後移出安全關鍵路徑（fe2b252） | Leo 指示（spec：superpowers/specs/2026-07-14-agent自我進化-每晚反思與策略記憶-design.md） | L |
| 辛-3 | ✅ 完成（2026-07-14）：web_search 上網查證工具——依主題套網域白名單＋`web_search_lookups` 查證紀錄三件套＋金鑰未設優雅降級 | Leo 指示（spec：superpowers/specs/2026-07-14-web-search上網查證工具-design.md） | M |
| 辛-4 | ✅ 完成（2026-07-16，PR #54）：自適應問候時間——`greeting_preferences` 三件套＋純統計計算核心（死區防自我實現漂移／護軌 6–11 時／往後 60 分往前 30 分不對稱容忍）＋問候 job 改每半小時掃描（`greeted_today` kind 濾網冪等）＋記帳 at-most-once（失敗跳過本輪）＋`PROACTIVE_GREETING_*` 七鍵啟動即驗證＋`proactive/constants.py` 分層修正 | Leo 指示（spec：superpowers/specs/2026-07-16-每位長輩的問候時間-design.md） | L |
| 辛-5 | ✅ 完成（2026-07-17，PR #55＋後續）：長輩目前地點——`elder_locations` 表（地名＋模糊座標，一人一列 upsert、既有庫 ALTER 升級）＋`LocationFacts` 注入（過期 2h 不注入、措辭「僅供參考」）＋`/turns` 位置三參數（三者齊備才寫、排在 dispatch 前）＋App 裝置端模糊化 0.01 度（精確座標不離開手機）＋`LOCATION_STALE_AFTER_HOURS` | Leo 指示（spec：superpowers/specs/2026-07-17-長輩目前地點-design.md） | L |
| 辛-6 | ✅ 完成（2026-07-17）：天氣地點正確性——工具收座標直查跳過地理編碼＋地理編碼限台灣（countryCode=TW）＋拒答模型臆測地名（`turn_context.elder_utterance` contextvar 比對長輩原話）＋系統提示「位置是參考不是答案」三句＋anchoring 探針 `scripts/anchoring_probe.py` | Leo 指示（spec：superpowers/specs/2026-07-17-天氣地點正確性-design.md） | M |
| 辛-7 | ✅ 完成（2026-07-17，PR #56）：JS 端 linting——frontend ESLint 9 flat config（tseslint＋react-hooks 7）＋app eslint-config-expo；順修 usePolling render 期改 ref 與 admin 七頁 effect 同步 setState；納入 CI（frontend／app job） | Leo 指示（spec：superpowers/specs/2026-07-17-js端引入linting-design.md） | M |
| 辛-8 | ✅ 完成（2026-07-17，PR #57）：JS 端測試基建——frontend vitest 4（jsdom）＋app jest-expo；4 測試檔（useLoadable／usePolling／MemoryTab／location 四條靜默降級）；新增 `useLoadable` 收斂 admin 七頁載入邏輯；JS 測試納入 CI | Leo 指示（spec：superpowers/specs/2026-07-17-js端測試基建-design.md） | M |
| 辛-9 | ✅ 完成（2026-07-17）：主動問候接續昨天話題——`ConversationSummaryStore.get_for_date` 三件套＋`CareAgent.proactive(recall=)` 一物二用（取代 intent 當長期記憶檢索關鍵字＋直接注入 prompt）＋`worker._yesterday_recall` 接線（讀取失敗只降級不擋問候）；早安與失聯關心同時受惠；順帶載明 Mem0 `MemoryItem.date` 晚一天（另案未修） | Leo 指示（spec：superpowers/specs/2026-07-17-主動問候接續昨天話題-design.md） | S |

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
| — | **內測基礎建設**（D-73，spec 2026-07-12，批次外插單）：內測總開關＋App 一機雙端快切＋後台四類數據與手動觸發　✅ **2026-07-12 完工**（PR #45；三計畫見 docs/superpowers/plans/2026-07-12-內測基礎-批1～3）——內部測試自此可開跑 |

## 變更紀錄

| 版本 | 日期 | 變更 |
| :--- | :--- | :--- |
| v1.0 | 2026-07-08 | 初版：六批 40 工項＋里程碑；順序經 Leo 核准；分工待會-16 |
| v1.1 | 2026-07-09 | 會議決議回填：己批填入 8 個實際工項；分工＝Leo 單人（會-16）；乙-3／丁-3／丙-6 加 D-71／D-72 連動標註；彩排改暫定 |
| v1.2 | 2026-07-09 | D-71 三細節回填：乙-3 改 token 永久化（不做效期）；丁-3／己-6 解鎖 |
| v1.3 | 2026-07-10 | 戊批完工標記：CI 五 job＋覆蓋門檻 80%（現況 87%）、KPI 量測基建（token／往返 P50/P95／危急 P/R）全數落地 |
| v1.4 | 2026-07-12 | **新增庚批**：架構文檔深化（七群深潛）發現的 58 項後端＋8 項前端差距開成 56 個工項，分七區（立即修 HIGH 9／正確性 10／安全強化 7／前端 7／清理 13／待決策 3／範圍外文檔 7）；標註兩項深化中已解決（A-12 誤判、F-8 已補圖）。庚批未排入 8/20 時程，建議至少完成庚1 |
| v1.5 | 2026-07-12 | **內測基礎建設完工**（D-73，批次外插單，PR #45）：批①總開關＋meta＋.env 整理、批② App 雙 slot 快切、批③後台五分頁＋系統頁＋手動觸發；里程碑表補完工列 |
| v1.6 | 2026-07-12 | **新增辛批**（Leo 逐項指示的發表前功能補強）：辛-1 App 用藥回診編輯完成（App 12 頁，見 17 v1.6／12 v1.3） |
| v1.7 | 2026-07-13 | 庚批 56 項結案回填（追認補記——當時 commit 未同步版頭與本表） |
| v1.8 | 2026-07-17 | 辛批補記 7 工項並全數結案：辛-2 每晚反思、辛-3 web_search（7/14）、辛-4 自適應問候時間（7/16）、辛-5 長輩地點、辛-6 天氣正確性、辛-7 JS lint、辛-8 JS 測試基建（7/17）；標記庚-09 結案矛盾（55/56，待 Leo 確認） |
| v1.9 | 2026-07-17 | 新增辛-9 主動問候接續昨天話題（讀昨天對話摘要當檢索關鍵字＋直接注入；否決 Mem0 昨晚整理項的理由見 spec）；D-33「摘要無讀取端」現況自此失效（07 v1.3 同步） |
