# WBS 開發計畫（一次性重構）- 金孫 KinSun

> **版本:** v1.45 | **更新:** 2026-08-09 | **狀態:** 新增辛-30＝網頁版補齊新視覺六批（發表要用網頁做 demo；W1 token 與文案、W2 共用元件已完成，W3～W6 待續）；新增辛-31＝六批範圍外的人設洩漏收尾（通道層兩句提示、摘要提示詞與每晚反思提示詞改阿白，LINE 選單的服務名保留），已完成。辛-28＝KinSun 新視覺六批交接，批次 1～6 真實契約版已完成（批次 5～6 Android Expo Go 可觸達資料態已驗收；摘要有資料態與通知 badge 由自動化覆蓋；認證競態已修）；後續完整契約列辛-29；辛-27（原 Jerry 分支辛-23，因與 main 的辛-23 撞號而重編）＝正式 `/elder/talk` 整合核准 Prototype 視覺與 WS 狀態收尾，已完成；辛-26 第二段完成（**F-17 結案**：`location.ts` 恢復取位＋`useTalk.ts` 新增獨立暖權限 mount effect；天氣／附近地點完全解除，路線恢復到與 App 版同精度）。web 573→**585**；辛-25 審查後補完四項（🔴 補播引入的續拉錯亂已修——第一版誤記為「非本輪造成」，探針實測推翻；字幕被新一輪搶走已修；2 Minor）。web 573→**578**；新增辛-26（**F-17 第一段：縣市座標反查模組已備妥、尚未接線**，Leo 2026-08-01 八項裁決的第 6 項，⏳ 部分完成）：`web/src/elder/countyCoords.ts`（複製後端 `_COUNTY_COORDS`＋Haversine 最近鄰查表）與 `scripts/verify-county-coords.mjs`（防兩份表漂移，掛進 `npm run build`）；`location.ts`／`useTalk.ts` 刻意未接線（T4／T6 當時同支 `useTalk.ts` 收尾中）。web 563→**573**；新增辛-25（**對講機兩項裁決同時施工**，Leo 2026-08-01 八項裁決的第 3、7 項，已完成）：iOS 音訊解鎖提早到「播放器誕生後的第一個觸碰」＋插嘴後前一題的答案改為補播（推翻 2026-07-31 的「一律丟棄」）。web 553→**563**；新增辛-24（**危急警報看起來像危急警報**，D-80，已完成）：`app_notifications` 加 `severity` 欄，橫幅與兩支清單畫面同步分級；T3 審查補完三項（長輩欄接線補對稱測試、認不得值改 `console.warn` 留痕、對比度數字更正）。Python 2653→**2672**、web 517→**553**；辛-23 審查後補完四項（F-19 結案、鐘點範圍驗證、兩處訊息補正）；新增辛-23（修回診「前一天」提醒提早兩天響＋下午設明天的回診整筆建不起來，D-79，已完成；`meta.warnings` 前端顯示與兩份凍結前端的顯示面根因兩項未處理）；庚-11（A-10 有字無聲）2026-07-29 由「不改」改判並完成；新增辛-22（修未註冊工具導致的退化輸出，A＋C 兩層已完成、B 提示詞動態化留待辦）；新增辛-21（一輪總時間預算 `TURN_BUDGET_SECONDS=30`，已完成）；新增辛-20（修對講機改走 WS 後定位失效，已完成——App 端位置鍵名未依線路契約改名，位置整晚沒寫進庫）。第 5 層 RAG 正式化、版本發布、單庫原地遷移與個人 Supabase 驗收均已完成；active release、獨立週更 Worker、Agent 查詢與 Admin citation trace 已實測。甲～庚批、內測基礎建設（D-73）與辛批 14 項其餘狀態維持原表（辛-13 全流程模擬實測、辛-14 三項修復完成）。新增辛-17（工具回合思考層級，已完成）；新增辛-18（附近地點搜尋，已完成——`places` 表＋工具＋三道結果後處理；人工真 LLM 驗證 18/18 全對，並追加修復驗證發現的 `place` 距離護欄 Critical）。
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
| 戊-3 | ✅ 完成（2026-07-10）：worker 接線 100%＋app.py 組裝根 97%＋LineApiMessenger 100%＋rag 支援四模組 100%；pytest-cov 上 CI（--cov-fail-under=80，2026-07-18 實測 88.24%） | M-8 | M |
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
| 己-7 | ✅ 完成（2026-07-18）：唯讀 migrate dry-run／原始資料備份／重切重嵌入、版本化候選、golden set 品質閘門、原子發布與 rollback；個人 Supabase 已發布 `rag-20260718T055933Z`（790 文件／2,808 chunks，threshold 0.65，recall 100%、false-positive 0%、安全 100%、citation correctness 90%），Agent→RAG→Admin citation trace 與獨立週更 Worker 均已驗收。 | D-03（會-14） | M |
| 己-8 | ✅ 完成（2026-07-10，範圍 Leo 核可）：revoke_consent 刪除；can_view_transcript 方法＋欄位全刪（冪等 DROP）；escalation_order 保留（家屬排序仍用） | D-13／09／10 | S |

無需工項的決議：會-6 詞表（實測時滾動加）、會-7 門檻數值（實測再調）、會-11 問候維持文字、會-15 麥克風文案照現值；會-8／9／10／13 擱置、會-12 掛起。

## 庚、架構文檔深化發現修復批（2026-07-10 深潛新增，未排入時程；待 Leo 定優先序）

> 來源：[2026-07-10 架構文檔深化](../superpowers/specs/2026-07-10-架構文檔深化-design.md)——七群逐模組深潛，登記 58 項後端差距（[05 差距表](05_架構與設計.md#差距與重構項本文件貢獻給-16_wbs)的 A-8～A-58）與 8 項前端差距（[12 §9](12_前端架構規範.md) 的 F-8～F-15）。**全部只記錄未動代碼**。下表把每項開成工項並標「問題編號（A-xx／F-xx）」以對應 05／12 細節。批內順序＝建議施工序（HIGH 先）。

### 庚1 立即修（HIGH，9 項）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-01 | ✅ 完成（2026-07-12，TDD）：pipeline 落庫門檻放寬至 ≥L1（通知維持 ≥L2），D-10 己-5「L1 小訊號進每日摘要」生產路徑生效；契約測試改寫＋全套 591 綠。已知副作用：健康報告出現「關注」級事件（本無 tier 過濾，接受；不想顯示另開工項） | A-39 | M |
| 庚-02 | ✅ 完成（2026-07-12，TDD）：admin overview 新增 `guardian_notification_failure` 告警——近 60 分鐘任一筆 `delivered=False` 即紅字橫幅（門檻 1，不設噪音緩衝）；`RiskNotificationLogStore.count_failed_since` 三件套＋契約測試；OverviewPage 依 kind 分文字。採最小方案（Leo 拍板：不做重試／死信，發表期靠後台盯）。 | A-40 | M |
| 庚-03 | ✅ 完成（2026-07-16）：安全預設 `allowed_only` 阻擋非 ALLOWED；課堂以 `classroom_demo` 明確保留並在 Admin 警告。 | A-26 | S |
| 庚-04 | ✅ 完成（2026-07-12，TDD）：`bind_elder_device` redeem 前驗 `invite.role is ELDER`，家屬邀請碼回 409 `invite_wrong_role`（未消耗碼、未發 token）；06 端點表＋錯誤碼表同步 | A-46 | S |
| 庚-05 | ✅ 完成（2026-07-12，TDD）：`DELETE /api/v1/sessions/all`＋`AccountService.logout_all_devices`（撤該家屬全部 token），與長輩 `revoke_elder_device` 對稱；06 端點表同步 | A-47 | S |
| 庚-06 | ✅ 完成（2026-07-12，TDD，含庚-13）：`run_consolidation` 改吃 `(short_term, long_term, log, now)`——掃「上次整理日之後～今日之前」每個有對話的完整日，逐日 `list_for_range` 補整理；停機跨多日重啟不再漏天。新增 `MemoryStore.list_for_range`／`day_starts_with_turns`（Pg＋Fake）。worker／CLI 皆已接線。全套 627 綠。 | A-18 | M |
| 庚-07 | ✅ 完成（2026-07-12）：觀測五表（webhook_events／asr_calls／llm_calls／tts_calls／replies）`line_user_id` → `external_id`＋新增 `channel`，正名兼消除「line_user_id 混用」鐵律違反。含冪等 schema 遷移（DO 區塊守門 RENAME＋`ADD COLUMN IF NOT EXISTS channel`，新舊庫皆適用）、models／store（含 Fake）三件套、pipeline 全鏈 threading、邊界（inbound dispatch 取 `msg.channel.value`、LINE webhook 記 `channel="line"`）、admin `_trace_json` 回傳改 `external_id`＋`channel`、前端 TraceDetail 型別與頁面同步。`channel` 於 record 端預設 `""`（對齊 DB 欄預設）。契約測試補 channel round-trip、dispatch 測試證通道貫穿。全套 628 綠。 | A-8 | M |
| 庚-08 | ✅ 完成（2026-07-12，跨進程方案）：新增 `PgRateLimiter`（Postgres 共享滑動視窗，per-key `pg_advisory_xact_lock` 串行「清舊→計數→寫入」精確計數、掛鐘可跨進程、fail-open）＋`rate_limit_hits` 表；抽 `RateLimiter` Protocol，app.py 正式組裝改注入 Pg 版（記憶體版留測試／單 worker fallback）。多 worker 上限不再×worker 數。Pg IT 測試鎖「兩實例共用計數」。沿用既有 `AUTH_RATE_LIMIT_*`，無新增 env。 | A-54 | M |
| 庚-09 | ✅ 完成（2026-07-16）：RiskDetector 維持唯一權威，透過 ToolInvocationContext 傳入；RAG 旗標正名 `requires_safety_attention` 並留稽核。 | A-27 | S |

### 庚2 正確性與可靠性（MEDIUM）

| # | 工項 | 問題 | 規模 |
| :--- | :--- | :---: | :---: |
| 庚-10 | ✅ 完成（2026-07-12，TDD）：pipeline 新增 `_assess`——分級呼叫包進 token 收集器並補記 llm_call trace（model_name＝`GEMINI_MODEL_SAFETY`、fail-safe 以 `llm:error` 訊號記 error）。每輪 llm_calls 1→2 筆，分級 token 與生成筆分離（測試鎖定）。 | A-9 | S |
| 庚-11 | ⏸ 不改（Leo 2026-07-12：現狀可接受）——錯誤情境頻率低、螢幕有字；曾評估 expo-speech 裝置語音與預錄提示音兩案。<br>→ ✅ **2026-07-29 改判並完成**（Leo 指示，TDD，+11 條測試）。**兩個前提在 07-12 之後都變了**：①「預錄提示音」當時要從零建一套合成＋上傳＋過期管理，07-28 的安撫話快取（`speech/ack_audio.py`）已經把它整套做出來了——這次只是多注入一句 `standby_phrases`，規模由 M 降到 S；②「螢幕有字」對純語音長輩不成立（07-29 測試的 p7 白內障、看不到螢幕，實測回饋「伊有時陣攏無聲，干焦有字，我毋知伊有咧應無」）。**「頻率低」這一條仍然成立且未被推翻**——改判的理由是成本，不是頻率。作法見 [05 §8](05_架構與設計.md)。 | A-10 | M→S |
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
| 庚-21 | ✅ 完成（2026-07-16）：文件與查詢統一 `RAG_EMBEDDING_MODEL`，release 記模型＋768 維；不符停用向量。 | A-28 | S |
| 庚-22 | ✅ 完成（2026-07-16）：中文同義詞、疑問贅詞移除與 2～4 字 n-gram keyword fallback。 | A-29 | S |
| 庚-23 | ✅ 完成（2026-07-16）：版本化索引、原子發布、週更 Worker、RAG trace／Admin 稽核與品質驗收。 | A-30 | S |
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
| 辛-9 | ✅ 完成（2026-07-17）：主動問候接續上次話題——`ConversationSummaryStore.get_for_date` 三件套＋`CareAgent.proactive(recall=Recall)` 一物三用（檢索關鍵字＋注入情境＋任務條件式加碼追問）＋`worker._recall` 以 `last_active` 定位「她上次開口那天」＋真 Gemini 探針 `scripts/recall_probe.py`（三處設計皆由它逼出：定位日不可用「今天減一天」、`days_ago` 非帶不可、情境段不足以驅動行為）；早安與失聯關心同時受惠；一併修 Mem0 記憶日期晚一天（`occurred_on` 進 metadata＋排序改以對話日為主鍵） | Leo 指示（spec：superpowers/specs/2026-07-17-主動問候接續昨天話題-design.md） | S |

| 辛-10 | ✅ 完成（2026-07-25）：濫用審核（D-75）——`safety/moderation.py`（`AbuseModerator`＋`AbuseClassifier` Protocol＋`LlmAbuseClassifier`＋`FakeAbuseClassifier`＋類別對應口語回絕話術）只擋 role_hijack／system_disclosure／code_generation 三類，全路徑 fail-open＋信心門檻 0.7；管線接在**家屬通報之後**（`test_moderation_runs_after_family_notification`＋`test_blocked_turn_still_records_and_notifies_the_crisis` 雙重守住）；`SAFETY_MODERATION_ENABLED`／`_MIN_CONFIDENCE` 兩鍵，**預設開**（Leo 2026-07-25 核定；⚠️ 據以核定的數字已同日作廢，見 D-75）。同時新增 evals `careline-prompt-injection`（32 題五類含 benign 對照組＋四項自訂 GEval，跑真 CareAgent 不需 DB），旗標開關切換即產出可比對的 `-moderated` 實驗。⏳ 待配額重置後以可信裁判重跑（辛-11 的三項防呆先做） | Leo 核定（組員 Godzilla-z 研究產出 `DecisionEngine.py` 評估後重寫接法，見 D-75） | M |

| 辛-11 | ✅ 完成（2026-07-25）：觀測與評測強化五項——①`llm_calls.kind` 區分三種 LLM 呼叫（agent／risk_classify／moderation），後台延遲改逐種類分列（加入審核後，短呼叫會把整表 p50 拉低，讓「每輪變慢」顯示成「LLM 變快」）＋既有庫升級測試（實連測試庫，並確認拿掉遷移會紅）；②`speakable` 改為確定性檢查（`evals/assertions.py`，Opik 自訂指標＋promptfoo assertion 共用），免額度、免限流、可進 CI；③以 flash-lite 重跑基準線；④promptfoo 開啟 `crescendo` 多輪 strategy＋provider 補多輪對話解析（`parse_turn`＋`workers: 1`，否則多輪會靜默退化成單輪）；⑤`safety.evaluation` 加 `--model` 旗標，可同一份標注集比較模型 P/R（`GEMINI_MODEL_SAFETY` 自 D-16 未經驗證） | Leo 指示（五項推薦全採納） | M |

| 辛-12 | ⏳ **未施工**：評測可信度防呆三項（2026-07-25 發現 LLM 裁判會安靜給出假數字後開立）——①`no_system_leak` 改為確定性檢查（比對回覆是否含 `SYSTEM_PROMPT` 的長 n-gram／模型名／金鑰形狀，我們手上就有 prompt 全文，比 LLM 裁判準且免費）；②**指標變異數為零即報錯**（當日 32 題含攻擊與純閒聊全給 0.5，這條規則會當場擋下）；③**配額耗盡要大聲失敗**（現況是照樣「跑完」並產出看似正常的報告）。做完前，任何 LLM 裁判數字都不得用於決策——含 D-75 旗標預設值的定奪 | 2026-07-25 評測事故（見 D-75） | S |
| 辛-13 | ✅ 完成（2026-07-26）：**全流程模擬實測**——模擬三個台灣家庭（家屬×3、長輩×3，含無稱謂無排程、輕度失智兩種邊界人設）跑 106 場文字劇本＋20 場真語音回圈＋15 項瀏覽器點擊，資料全進拋棄式測試庫（D-69）。抓到兩項離線測試永遠驗不到的缺陷並修復＋補回歸測試：①每晚反思自 7/20 起全數失敗（對話以模型回合結尾，gemini-3.5 回 400）；②`/turns` 佔住事件迴圈（實測對話中 healthz 要等 2.89 秒＝一次只服務得了一位長輩）。另記錄 4 項嚴重（含危急誤報實際送達家屬、衛教回覆冒用「國健署網站說」）與 10 項中等問題，見 [實測報告](../2026-07-26_全流程模擬實測報告.md) | Leo 指示（自動化實測所有流程） | L |
| 辛-14 | ✅ 完成（2026-07-26）：**全流程模擬實測三項修復**（Leo 指示「這三個」）——①危急誤報：症狀詞撐住的 L2 改為「分級器沒故障、有把握、判定低於 L2 時降 L1（留痕不通知）」，絕對詞與故障 fail-safe 兩條紅線不動；②來源冒用：提示詞去掉可照抄的來源例句＋新增 `turn_context.turn_sources()` 本輪來源登記簿＋`agent._no_fake_source()` 出站防線（閘門是「有沒有拿到來源」而非「有沒有呼叫工具」）；③排程假死：`db.py` 連線加 TCP keepalive（根因）、`GET /admin/jobs` 逾期告警（可觀測）、問候與失聯關懷加補跑時限 240 分（重啟安全）、交付 `deploy/kinsun-scheduler.service`（**尚未安裝**，安裝前須確認補跑影響）。總測試 1769→1808 | Leo 指示（實測報告 S3／S4／S5） | M |

| 辛-15 | ✅ 完成（2026-07-27）：**架構對比（`ref/hermes-agent`）後的六項邊界補強**（Leo 核可 1～5 全做）——①`tools/schedules.py` 安全界線 4：主動關懷回合（長輩沒開口）不得建立或取消提醒，端到端實測證實一次早安問候就能寫進一筆長輩從未答應的提醒；②`config.py` 語音後端白名單（打錯字改為啟動失敗，不再靜默降級成回傳寫死文字的替身）；③危急通知未綁通道與真失敗分流（`risk_notification_logs.outcome`，修好被常態雜訊灌滿的告警）；④新增 `logging_setup.py` 單一入口（webhook 主行程先前完全沒有 logging 設定）；⑤LINE API 五個呼叫補逾時＋關掉 urllib3 隱形重試、出站補有界重試（逾時一律不重試）；⑥情境組裝 15 秒等待上限（mem0 無逾時可設）。新增測試 46 條，總測試 1884；`outcome` 欄已在真 Postgres 驗過既有庫升級路徑 | 架構對比報告（`.claude/context/decisions/architect-2026-07-27-0024-hermes-agent-架構對比.md`） | M |
| 辛-16 | ⏳ **未施工**：架構對比報告的第二批（NEXT）——LINE webhook 事件去重（**須先查證 LINE 後台重送設定是否開啟**）、工具 dispatch 失敗字串帶例外類型而非訊息內容、測試行程密封（`conftest.py` 目前無條件`load_dotenv()` 把正式 .env 的 103 把鍵灌進測試行程，LINE token 這一側無防線）、工具派送埋點停止把長輩健康資訊送進 Opik（**需 Leo 對「工具參數可否進 Opik」表態**）、清三處死碼（`tools/lookups.py` 的 `list_recent` 在 src/ 零呼叫端卻養著一張無人清理的表）、LLM 錯誤最小分類＋只在排程端加退避重試 | 同上 | M |
| 辛-17 | ✅ 完成（2026-07-27）：**工具回合補思考層級**——Leo 回報「好像無法調用工具」，查 Opik 定案根因為 `llm.py::generate_tool_turn` 從未設 `thinking_config`，而 07-25 平移升版到 `gemini-3.5-flash-lite` 之後預設思考層級已不足以讓模型選工具：不報錯，改成**用講的代替查**（07-27 App 對話 0/7 該查沒查，且重放時編出三個不同的拉麵店名）。改為 `TOOL_TURN_THINKING_LEVEL="MEDIUM"`（原封重放 5/5，延遲 1.0s→2.33s，Leo 核可；HIGH 同為 5/5 但多花 1 秒買不到東西）。新增測試 2 條，總測試 2047，並以真 API 走完整 `GeminiClient` 路徑驗證 3/3。⚠️ 一併記錄兩件未處理：①長期記憶 embedding 每天撞免費檔位 429（07-27 共 113 次，每次靜默退化為無記憶）；②模型沒查到時會自行編造店名，出站冒名防線只擋機關名稱 | Leo 指示（查 Opik 追工具失效） | S |
| 辛-18 | ✅ 完成（2026-07-27）：**附近地點搜尋**（`search_nearby_places`）——承接辛-17 記錄的「②模型沒查到時會自行編造店名」：實錄長輩問「我家附近的拉麵店」，`web_search` 查出的是 2.9 公里外的板橋分店，模型仍照唸不誤。新增 `places` 表（Overture Maps 台灣 POI，2026-07-27 灌入正式庫 285,140 列／153 MB）與 `places/` 模組（models／geo／store／categories／refine／ingest）；新增工具 `search_nearby_places`（半徑固定 1500 公尺、查無結果**不放大**——放大會把長輩指到分店；`elder_id` 只認 `ToolInvocationContext`、座標由工具自行向 `LocationStore` 取不經模型，比照排程工具的安全界線；結果經「剔除可疑座標→去重→店名清洗」單一入口 `refine()`）；開放 15 個長輩口語類別，`chiropractic`（問「按摩」）Leo 核定只收整復／國術館／推拿，刻意排除泛稱的「按摩」——實測會撈到性產業與寵物 SPA 招牌。同步收窄 `web_search` 職責（SYSTEM_PROMPT 與 tool description 皆排除「附近的店家與場所」）。順手修正 `locations/store.py` 檔頭與程式碼矛盾的敘述（已被 2026-07-17 天氣地點正確性設計推翻）。✅ 人工真 LLM 驗證（真 Gemini＋正式庫資料）：工具選擇 18/18 全對，回歸無誤（新聞／天氣未被搶走）；⚠️ 驗證追加發現一個單元測試測不到的 Critical——模型會把**店名**當 `place` 傳入，Nominatim 對店名照單全收（「麥當勞」解析到台南，離長輩 254 公里），已修復（`_MAX_PLACE_METERS=50_000` 距離護欄＋回傳講出中心點地名＋收窄 `place` 參數說明）。全庫測試 2137 passed（含 `KINSUN_IT=1`） | Leo 指示（2026-07-27 06:00 實錄長輩對話，spec：superpowers/specs/2026-07-27-附近地點搜尋-design.md） | L |
| 辛-20 | ✅ 完成（2026-07-28）：**修對講機改走 WebSocket 後定位失效**（承接辛-19，該工項記錄見下方版本歷程 v1.21）——Leo 回報「問地點金孫一直反問我人在哪裡」。查 Opik 定案根因為 App 端 `lib/talkSocket.ts::sendLocation` 直接 `JSON.stringify(ElderPlace)`，線路鍵名成了本地欄位名 `place`，而後端 `channels/app/ws.py::_parse_location` 依契約讀 `location`，恆為空字串→`_save_location` 的 `not place` 提前 return，`elder_locations` 一列都沒寫。位置一過 `LOCATION_STALE_AFTER_HOURS=2` 即不再注入情境，金孫遂照 `agent.py` 的「沒位置一律先問、不猜」開口問——**反問是設計，鍵名才是 bug**。證據鏈：正式庫最新位置停在 07-28 11:19（WS 上線前）、Opik memory_assemble 自 17:58 起 20 餘輪全無位置段落（07-27 13:26 與當日 11:17 皆有）、後端日誌 17:51 重啟後只有 WS 零筆 `POST /turns`（鍵名正確的降級路徑沒被走到）。⚠️ 兩邊單元測試各自斷言自己那一版契約（後端送 `{"location":…}`、App 斷言 `{place:…}`）所以全綠——修法連同把 App 測試改成斷言**線路鍵名**，那才是能擋住這類縫的斷言。App 端 34 passed＋tsc／eslint 全綠，後端 WS／POST 兩路徑 34 passed | Leo 指示（2026-07-28 查 Opik 追定位失效） | S |

| 辛-21 | ✅ 完成（2026-07-28）：**一輪對話的總時間預算**（`TURN_BUDGET_SECONDS=30`，Leo 核可只做這一條）——承接同日 Gemini 3.5 過載實錄：一輪依序打三次 Gemini（分級→審核→生成），逐次 30 秒逾時攔得住一次呼叫、攔不住三次**相加**，實錄長輩按完對講機盯著螢幕 **96.6 秒**才聽到回退話術（asr 7.0s ＋ risk 29.7s ＋ abuse 29.8s ＋ agent 29.6s）。作法：`turn_context.turn_budget` 新增 deadline contextvar（走 contextvar 而非明式傳參——後者要改 `assess`／`moderate`／`handle` 等六七個簽名與其全部測試替身，而真正需要它的只有 `llm.py` 一處出口），`GeminiClient` 兩個出口取 `min(GEMINI_TIMEOUT_SECONDS, 本輪剩餘)` 為該次逾時、預算用完直接拋 `LLMError` 不打出去。⚠️ 刻意**不新增降級分支**：三個呼叫端早已各自備好 LLM 故障的路徑（分級 fail-safe 留痕／審核 fail-open 放行／生成回退話術），走同一條即可。預算自**收到音檔**起算、含 ASR——長輩等的是「按完到聽見」，排除 ASR 會讓說好的 30 秒實際變成 37 秒。取捨已量化：歷史 68 輪 p95 為 19.8 秒、僅 2 輪超過 30 秒（46.0s／96.6s，兩輪都已經是壞的），故上限砍不到正常對話。`0`＝不限制（維運逃生口，回到逐次逾時的舊行為）。新增 13 條測試（turn_context 4／llm 5／pipeline 4），全庫 2287 passed、ruff 全綠 | Leo 指示（2026-07-28，只做總預算不做安全檢查併行） | S |
| 辛-22 | ✅ 完成（2026-07-28）：**修未註冊工具導致的退化輸出**（2026-07-26 延遲優化報告 §7 順帶發現、§8 候選；Leo 2026-07-28 核定做 A＋C 兩層、B 留待辦）——提示詞寫死點名 `web_search` 等工具，而它們是**條件式註冊**（Tavily 金鑰／TDX 憑證／兩個 store 缺一就跳過）。工具沒註冊時模型不會說「我沒有這個工具」，而是**假裝呼叫**：吐出 `tool_code\n{...}` 並無限重複（實測單則 186,514 字）。既有出站防線整段放行（`_speakable` 只認以 `{`／`[` 開頭者），這坨東西一路送進 TTS→唸不完撞 30 秒逾時→`pipeline._synthesize` 退化成無音檔→**長輩按下對講機等三十秒、完全沒有聲音**，而完整回覆照樣寫進字幕、記憶與觀測（下一輪還會被 `recent()` 帶回上下文）。修法兩層：**A 出站護欄**——`_speakable` 加 `_TOOL_CALL_LEAK`（`tool_code`／`print(`／`default_api.` 開頭；**code fence 的語言標籤也要認**，`tool_code` 正寫在標籤位置，只看拆殼後的內容會把它當合法 JSON 打撈——這是實作時測試才抓出來的）直接退 `SYSTEM_TROUBLE_REPLY` 且不打撈（撈出來的是工具參數，單獨唸更莫名其妙），加 `_MAX_SPEAKABLE_CHARS=500` 通用長度網（TTS 0.9s＋每字 0.10s，30 秒逾時≈291 字，故被殺掉的回覆本來就已經是壞的；分段通道只合成第一段故留兩倍餘裕）；**C 組裝對帳**——`build_tool_registry` 結尾比對 `SYSTEM_PROMPT` 與實際註冊表，有缺口就 warning（工具名字面掃描 `AUDITED_SPECS` 不手寫清單、交通三工具因提示詞只描述不點名故另列 `_PROMPT_IMPLIED_TOOLS`、另有一條掃 `kinsun.tools` 全部 ToolSpec 的防腐化測試）；只警告不讓啟動失敗，優雅降級是刻意設計。⚠️ 修的是**程式層的地雷、不是當下故障**：本機三個金鑰皆有設定故觸發不到，金鑰過期／換機器／新同事未設 `.env` 才會踩到。⚠️ 一併更正 `agent.py` 一條被實測推翻的註解（原寫「未註冊時模型自然看不到該工具，故 prompt 提及也無妨」）。**未做（B）**：提示詞依實際註冊工具動態生成——治本但要拆寫死字串並處理 Opik prompt 版本註冊，Leo 核定留待辦。新增 13 條測試（agent 7／composition 6），全庫 2274→2287 passed、ruff 全綠 | Leo 指示（2026-07-28，問「這個有修好了嗎」後核定 A＋C） | S |
| 辛-23 | ✅ 完成（2026-08-01）：**修回診「前一天」提醒提早兩天響＋下午設明天的回診整筆建不起來**（D-79，兩項當成同一個改動）——根因是三份前端共用的那段推算把本地時區解析出的 `Date` 用 `toISOString()`（UTC）取日期，在 `Asia/Taipei` 少算一天，而後端 `parse_occurrences` 把 client 的日期**原封不動**存進庫、不重算。裁決為**改後端**：新增 `timeparse.build_appointment_reminders` 成為 REST 與 LINE 共用的唯一一份推算，REST 對 `kind=appointment`＋`event_date` 忽略 client 的 `occurrences`（含鐘點，改吃 `APPOINTMENT_REMINDER_HOUR`）——一次修掉三個前端含兩個凍結的，往後新 client 也不會再犯。第二個症狀連帶解決：已過期的「前一天」那顆改為略過而非讓服務層擋掉整筆，並以 `meta.warnings`（REST）／回覆句後綴（LINE）告知家屬**不靜默**。**審查後同日補完四項**：①**F-19 結案**——`web/` 接上 `requestWithMeta` 並把 `meta.warnings` 顯示在既有的 `NoticeText`（⚠️ `setHint` 必須排在 `resetForm()` 之後，順序顛倒會被當場清掉且畫面看不出異狀）；②`APPOINTMENT_REMINDER_HOUR` 補 0–23 範圍驗證（誤設 24 原本讓每筆回診建立回 HTTP 500——REST 只攔 `TimeParseError`，而 `ValueError` 反向不成立；接管前這個洞只在 LINE 路徑）；③兩顆都過期的 400 訊息改講真正的原因（原句叫家屬確認一個沒錯的欄位）；④**新增與編輯回傳不同的句子**（編輯時前一天那顆很可能已經正常送出過，沿用新增那句等於叫家屬去做系統已經做過的事）。⚠️ 仍未處理：兩份凍結前端的 `isoDate` **根因未除**，`describeGroup()` 的回診日期與自訂一次性提醒兩處**顯示**仍少一天（純顯示、後端無從代勞，12 §9 F-16），`app/`／`frontend/` 也看不到警語。新增測試 27 條（Python 19：timeparse 7／wording 4／flow 2／api 8／config 2；web 8：api 5／screen 3），變異驗證 36 次全數變紅（含一次「等價變異」追查與一次變異本身寫壞的更正，見報告）；22 支 Python 測試檔逐支跑過全綠（含 `KINSUN_IT=1` 的 PG 合約與 schema），`ruff check`／`format --check` 全綠；web `test` 517／`typecheck`／`lint`／`build`／`audit`（0 漏洞）全綠 | Leo 裁決（2026-08-01）| S |
| 辛-24 | ✅ 完成（2026-08-01）：**危急警報在畫面上與「該吃藥了」毫無區別**（D-80）——根因指得出確切那一行：`app_notifications` 只有四個欄位，`notifications/store.py` 的 INSERT 沒有任何欄位能分辨這則是危急警報還是用藥提醒，前端拿到的就只有一段文字。修法是後端加 `severity`（`notice`／`alert`，刻意不沿用 `RiskTier`，理由見 `notifications/models.py` 檔頭），經 `ChannelRouter` 原樣轉交各通道 adapter（LINE 明文忽略、App 落庫）；全庫只有 `safety/notifier.py` 送 `alert`。前端三條互相獨立的路徑同時改變——紅底白字、`role="alert"`／`aria-live="assertive"`、標題改「緊急通知」——缺一就只有一部分人分得出來；**清單兩支畫面**（長輩端與家屬端）同步加紅框＋「緊急通知」文字標籤（WCAG 1.4.1：顏色不可是唯一手段）。既有庫由 `ensure_schema` 以 `ALTER ... ADD COLUMN IF NOT EXISTS` 就地升級，兩支 PG 整合測試造出四欄舊表＋舊資料重現該路徑（空庫測不到）。⚠️ 已知限制：2026-08-01 之前寫入的舊列一律 `notice`，無從回溯分辨。⚠️ 待真機驗收：`aria-live` 屬性在同一次 DOM 變更裡切換的實際播報行為未經驗證。Python 2653→**2672**、web 517→**553** |
| 辛-25 | ✅ 完成（2026-08-01）：**對講機兩項裁決同時施工**（Leo 2026-08-01 八項裁決的第 3 與第 7 項，兩者都動 `web/src/elder/useTalk.ts`，合併一輪避免衝突）。**①iOS 音訊解鎖提早（選項 B）**——`docs/dev/17` §6 記載 2026-07-18 的真實故障「播放與錄音搶同一音訊工作階段，iPhone 錄音全數 ≤0.72 秒近無聲」，而網頁版把解鎖掛在 `pressIn` 第一行（按下去→播 50ms 無聲檔→立刻開錄）是**同一個形狀**。改為在建立播放器的那條 effect 掛 `window` `pointerdown`（capture）一次性監聽器，解鎖「這顆播放器誕生之後的第一個觸碰」，麥克風鍵保留補漏呼叫。⚠️ **查證後推翻交辦的直覺做法**：不可能掛在配對／登入畫面的按鈕上——那一刻播放器還不存在，而 iOS 的解鎖綁在單一 `HTMLMediaElement` 上，對別顆解鎖等於沒解鎖。⚠️ 搬到 `window` 上會新增「解鎖把正在播的那一則當場切斷」的風險，已用兩道守門擋住。⚠️ 殘餘風險（第一個動作就按麥克風時形狀不變）無法在無頭環境判定，人工驗收 A1／A1b／A1c 已改寫。**②插嘴後前一題的答案改為補播**（推翻 2026-07-31 的「一律丟棄」裁決）——收音期間抵達的回覆改為收進暫存、`recorder.stop()` 真的回來之後才放回播放佇列（**「收音中不放音」那道 Critical 保護一行未動**）；FIFO（舊答案先播，填掉等新答案的空白）、上限 2 則（一輪最多 ack＋reply，防止連續插嘴累積成一串舊語音）、三條非補播出口都要清暫存；新增 `playback.ts::revokeReplyAudio`（`revokeQueuedReplyAudio` 是「除了這一則以外全部回收」、只留得住一個例外，而等補播的是複數）；`strings.talk.thinkingAfterSkipped` 移除（會補播就代表「跳過了」是假話）。⚠️ 一併載明一項非本輪造成、未修的落差：補播讓「舊回覆的續段接到新一輪」更容易發生（要修得替 `ChunkQueue` 綁 `turn_id`，屬另一個工項）。新增 10 條測試（解鎖 3／補播 7），逐條變異驗證——⭐ 其中一次**推翻了自己的預測**（原以為開錄失敗路徑的 `clear()` 已是等價變異，實測它與清暫存各自只讓一條測試變紅、兩者缺一不可），另一次確認 `revokeReplyAudio` 的 `blob:` 前綴守門確為等價變異而移除。web 553→563。**同日審查後補完四項**（1 Critical＋1 Important＋2 Minor）：🔴 **Critical——補播引入了一條可聽見的退步**，而第一版報告把它誤記為「非本輪造成的既有落差、只是更容易發生」：審查以探針在本輪程式碼上實測長輩聽到 `A-chunk0 → B-chunk1 → B-chunk0`（舊答案開頭→新答案**中段**→新答案開頭），再用 `git worktree` 回到補播之前的 commit 跑同一支探針得到完全正確的 `B-chunk0 → B-chunk1`——**是本輪讓一條原本不會發生的錯亂真的發生了**，而 `chunk_count > 1` 是預設狀況（`chunking.py` 的 `MIN_CHUNK_CHARS = 8`、回覆 p50 39 字）、觸發條件在「後端跑五到十秒、補播約八秒」的尺度下約是擲硬幣。修法：`ChunkQueue` 加 `turnId`、新增 `playingTurnIdRef`，`advanceQueue` 對不上就不接續段（`talkSocket.ts` 仍未動）。**Important——「字幕就是那一則自己的字」只成立約一秒**：`onFrame` 在收音狀態放開後就用新訊框的字覆蓋字幕，而舊答案還要播八秒；那正是本模組自己寫下要避免的事，而**對重聽長輩字幕是取得答案的另一半通道**，也是「補播不另加文案」唯一站得住的理由。修法 `canTakeOverSubtitle`（只擋「自己會帶著聲音出場」的字，錯誤／排隊／有字沒聲音的照顯示；只比對輪次，不做成一律等——同一輪的 ack→reply 字先出來是對的，已補測試釘住這個過度收斂）。**2 Minor**：解鎖守門①補上 `avatar === "speaking"`（`queue.isPlaying()` 涵蓋不到續段與 POST 降級路徑的播放）、17 摘要表補上解鎖殘餘風險的但書。再新增 5 條測試（含一條釘 `finally` 兩行順序的：`recorder.stop()` 擲例外時補播不可以被回呼再度收進暫存），逐條變異驗證。web 573→**578**、typecheck／lint／build／audit 全綠；後端未動 | Leo 裁決（2026-08-01，八項第 3、7 項）| S |
| 辛-26 | ✅ **完成（2026-08-01，分兩段施工）**：**F-17：長輩問天氣／附近地點不再反問所在地，交通路線恢復到與 App 版同精度**（Leo 2026-08-01 八項裁決第 6 項「好（天氣地名）」；對應 `docs/dev/12` §9 F-17 審查新增選項③）。**第一段（純函式，未接線）**：新增 `web/src/elder/countyCoords.ts`（逐鍵複製後端 `tools/weather.py::_COUNTY_COORDS` 22 縣市座標表＋Haversine 最近鄰查表；門檻 120 公里——寧可保守回 `null`、不硬配一個看起來最近的縣市，理由與實測數字見該檔檔頭：墾丁鵝鑾鼻離屏東縣代表點約 94.3 公里、蘭嶼離台東縣代表點約 37.6 公里皆在門檻內，東京約 2100 公里、沖繩那霸約 771 公里皆遠超門檻）；新增 `scripts/verify-county-coords.mjs`（比照 `scripts/verify-wasm-checksum.mjs` 防漂移精神，用純文字解析比對兩份表的字面值，掛進 `npm run build`）；`location.ts`／`useTalk.ts` 刻意未接線（T4／T6 當時同支 `useTalk.ts` 收尾中，避免兩個實作者同時改同一支檔案）。新增 10 條測試，web 563→573。**第二段（T4／T6 收尾後動工）**：`elder/location.ts::currentPlace` 恢復呼叫 `getCurrentPosition`，成功取得座標後用 `nearestCounty` 反查縣市名，連同**模糊化後的實際 GPS 座標**（非縣市代表點座標，理由同 App 版：真正決定天氣的是海拔不是行政區，附近地點搜尋更需要真實座標）一併回傳；反查不到或任一失敗路徑仍整組回 `null`。`useTalk.ts` 新增一條與 `probeMicrophone` **並列、獨立**的 mount effect 暖定位權限（不改寫既有那條、不動其相依陣列，把交叉修改面壓到最小）；`startRecording()` 既有那行呼叫保留不動——同一 origin 的定位權限只跳一次對話框，暖過之後開錄時的呼叫直接吃瀏覽器的位置快取，不會在錄音進行中再跳窗。⚠️ **查證後如實記錄三個症狀的解除程度不同，不假設「補上地名」三者一次全好**：天氣（`tools/weather.py`）與附近地點（`tools/places.py::build_nearby_handler`）都用得到 `LocationFacts` 注入的**實際座標**——`places.py` 的 `has_fix` 只檢查 `latitude`／`longitude` 是否非 `None` 且未過期，完全不看地名欄位——故這兩者**完全解除**；交通路線起點（`tools/transport.py::ROUTE_SPEC`）的 `origin` 參數**只收地名字串、沒有座標欄位**，模型把注入的縣市名經 Nominatim `geocode()` 轉回座標——這與 App 版**原本就相同**（App 的 `lib/location.ts` 回的地名同樣是 `city ?? subregion ?? region` 這種行政區層級字串，從未把座標傳給路線工具），故路線起點是**功能對等的解除**、不是精度退化。新增 6 條 `location.test.ts`＋4 條 `useTalk.test.ts` 測試（含暖權限 mount effect 的獨立性、與既有 `startRecording()` 呼叫共存等 4 項迴歸測試），逐條變異驗證，web `test`／`typecheck`／`lint`／`build`／`audit` 五項皆綠，web 573→**585**。⚠️ 人工驗收：定位權限的實際跳出時機、與麥克風權限的先後與觀感只能在真機驗證，已補進 `task-6-report.md` 的 77 項清單 | Leo 裁決（2026-08-01，八項第 6 項）| S |
| 辛-27 | ✅ 完成（2026-07-30 同步整合，2026-08-01 併入 main 時由辛-23 重編以免撞號）：**正式 `/elder/talk` 整合核准 Prototype 視覺**——保留正式 auth、裝置 token、WebSocket 對講與 `POST /turns` 降級、提醒鈴鐺、403 回退、位置、錄音／播放與雙手勢狀態機；加入正式 A-Kin 靜態插畫、頁面限定暖色 token、Phosphor 狀態／登出圖示、五態 presentation mapping 與單元測試，麥克風與鈴鐺沿用既有向量圖示。同步 main 後另修 WS 狀態收尾：共用播放器不再把 ack 播完誤判成整輪結束，ack→thinking、reply 最後一段→idle、error→高對比 error；舊播放收尾不得覆蓋新一輪 listening／thinking／error；TTS 降級成 `audio_url=""` 的純文字 reply 會在訊框抵達即回 idle，不等待不存在的播放完成事件。兩組狀態純函式共 6 條回歸測試釘住。Android Expo Go 54 以 393×852 邏輯尺寸驗證 idle、短按聆聽、長按放開、受控錯誤與登出取消流程；修正第一輪動作提示裁切後，核心控制均完整可見。 | Leo 指示（Prototype 測試完成後直接下一步） | M |
| 辛-28 | 🟡 **KinSun 長輩端×家屬端新視覺六批交接**（2026-08-07 起，逐批停下驗收）：✅ **批次 1 完成**——token／文案／人設／情緒黑名單與阿白離線 renderer 接縫；第一段實際開始播放即送文字與 `duration_ms` 對嘴，三支對講狀態機零修改。✅ **批次 2 完成**——Button／Field／Section／StatusPill／Chip、big 尺寸、長輩端 22px 無放大上限、48dp 觸控與 8 條元件測試。✅ **批次 3 完成**——`BearStage` 209×300 固定 top 140、四層一屏版面、系統字級 ≥150% 僅捲內容、主鍵 132→72 與回話卡 240ms 動畫、第一段即展開、完整回答播完收合；後端三條成功回應補 `transcript` 供長輩本人顯示真實「您說」，本機 `todayLog` 併發寫入與登出清除完成。App 批次 3 新增 12 條測試；後端既有四條回應測試補逐字稿斷言。✅ **批次 4 完成**——新增 `/elder/history`，只讀本機當日紀錄、最新在上、固定頁首／內容層捲動、返回保證回對講機；新增 4 條畫面測試。依使用者選項 1，尚無真實音訊契約前不顯示「再聽一次」。✅ **批次 5 完成，Android Expo Go 可觸達資料態已驗收**——家屬端改五項 Tabs；登入／註冊與詳情深頁搬至外層 Stack；中央新增提醒為 action、Android 非首頁返回 home、通知頁自行設定未讀 badge；第一位長輩暫用規則集中於 Provider，無長輩回 home。新增 3 支測試檔共 9 條；未新增 API、Schema 或套件。實機驗收發現登入／註冊在 `signIn()` 後立即 replace 會讓 Tabs 守門讀到舊的 `null` session；已改為等待 `SessionProvider` 實際提交 guardian session 才導向，新增 2 條回歸測試，登出後單次登入直接回首頁。✅ **批次 6 真實契約版完成，Android Expo Go 可觸達資料態已驗收**——新增純文字每日摘要切日／分享、獨立改回診日期時間／刪除與危急詳情安全降級；行程頁返回會重載，新增 4 支測試檔共 6 條。未支援的摘要結構化、`driver`／`notify_elder` 與危急完整契約另列辛-29。實機完成改回診／刪除的真 API 往返、摘要空狀態與危急安全降級；遠端測試帳號無摘要與未讀資料，日期箭頭／系統分享／通知 badge 由自動化測試覆蓋，不以空控制或 fixture 冒充完成。正式角色 PNG／speaking 向量素材仍待交付，現以既有暫用圖與 Otto renderer 驗結構。 | 使用者交接、2026-08-07「納入並連接」、「允許後端回傳 transcript」與第一位長輩裁決 | L |
| 辛-29 | ⏳ **新視覺批次 6 後續功能契約**（使用者 2026-08-07 指示未來要增加）：①摘要新增 optional `quotes`／`observations`／`stats`，產生端改結構化輸出且 `content` 向下相容；②排程補 `driver`／`notify_elder` 的明確儲存欄位、修改 API 與長輩告知時機，之後才顯示「誰帶去」與開關；③危急詳情補 `notification_id`／`risk_event_id`、GET／handle／dismiss、錄音播放、送達狀態、長輩聯絡欄位；④法務核稿後做 `consent_version` 重新同意，未同意只回原因／時間；⑤每次查閱稽核與 30 天逐字／錄音實體刪除排程。前後端型別、06 API、05／07 Schema、12／17 前端文件需同批同步；不得先以 fixture 或無效控制宣稱完成。 | 使用者 2026-08-07「好，但未來要增加這些功能」；`handoff/後端待辦-摘要拆結構.md`、`危急通知詳情-後端規格.md`、`同意條款修訂草稿.md` | L |
| 辛-30 | 🟡 **網頁版（`web/`）補齊新視覺六批**（使用者 2026-08-09 裁決：發表要用網頁做 demo，兩端視覺不可分岔）。辛-28 的六批交接從頭到尾只指名 `RAG/app/`，`web/` 完整停在改版前：色票仍是珊瑚橘、`strings.ts` 30 處把角色叫「金孫」、`elder/Avatar.tsx` 是 emoji、家屬端仍是 `useScreenStack` 無 Tabs、缺「之前聊過的」與批次 6 三支畫面。分六步對齊：**W1 token 與文案**、W2 共用元件、W3 對講機呈現層（阿白改接 Otto renderer——`pet-core` 本就是 web 技術，掛 DOM 不需 WebView）、W4 之前聊過的、W5 家屬端 Tabs、W6 家屬端新畫面。✅ **W1 token 完成**——`theme.css` 9→17 色＋五態光暈／狀態帶、舞台幾何、長輩端觸控尺寸、動畫時長與陰影；`theme.test.ts` 由「只驗 token 名字」改為兩層，新增一層直接讀 `app/src/lib/theme.ts` 逐一比對色值（色碼不寫死在測試裡，美術迭代仍只改 app 端那一份）——這正是本次漏掉的失敗型態：檔頭宣稱「值與 app 端完全相同」而 app 換色後 web 沒跟上，沒有任何測試會紅。41→55 條，`tsc`／629 條測試／`npm run build` 全過。✅ **W1 文案完成**——`strings.ts` 30 處「金孫」逐條分類：21 處改為阿白（長輩端自述用第一人稱「我」、狀態 aria-label 與家屬端用第三人稱「阿白」），10 處保留為服務名（品牌字樣、同意條款主體、「連不上金孫」、「用過金孫？」、服務狀態頁的 ASR／TTS 分項說明，以及「長輩手機上的金孫會被登出」——那個金孫是 App 本身）。新增 `strings.test.ts` 30 條，分兩組列舉：該叫阿白的地方不准殘留服務名、該是服務名的地方必須還在（不可用「全庫不准出現金孫」一條斷言了事，那正是鐵律 8 警告的錯誤做法）。連帶更新 7 支既有測試共 27 處寫死的舊文案期望值，並校正一處停在舊版的後端婉拒話 fixture（`ws.py::_BUSY_REPLY` 早已是第一人稱）。`tsc`／eslint 乾淨，42 檔 659 條測試全過，build 通過。✅ **W2 共用元件完成**——`ui/Button` 改暖黃膠囊配深靛藍字（舊版是磚橘底白字）、四 variant、56／84 最小高、按下縮放、busy 保留動作名稱、focus 2px 描邊＋2px 外偏移；`Field` 加 hint 並把家屬端標籤由 14px／textSoft 提到 16px／ink；`Section` 加 inset；`ErrorText` 改用 dangerText（鐵律 15）；新增 `StatusPill`（五 tone 三重編碼）與 `Chip`（硬下限 48px，選取狀態用 `aria-checked` 而非 `aria-selected`——app 端那支從交付稿繼承了 `selected`，web 直接做對）。**新元件當場接上呼叫端**，不留「寫了沒人用」：`SchedulesScreen` 兩組自寫 chip（提醒類型 radio、用藥時段 checkbox）改用共用 `Chip`，`InviteCard` 的綁定碼面板改用 `Section inset`。ui 測試 8→33 條，42 檔 675 條全過。⏳ W3～W6 待續。**架構待追認**：`otto-pet-core` 現住 `app/vendor/`，建議搬到已是三端共用包的 `shared/`，web 以 iframe 載入同一份 `renderer.html` 重用既有 bridge，讓情緒黑名單只有一份實作。 | 使用者 2026-08-09「要補，因為會用網頁做 demo」、「六批全補，web 與 app 對齊」、「直接掛 Otto renderer」 | L |
| 辛-31 | ✅ **六批範圍外的人設洩漏收尾**（使用者 2026-08-09 裁決）。辛-28 只改 `RAG/app/`，後端與通道層仍把角色叫「金孫」：`channels/inbound.py` 的 `NON_AUDIO_PROMPT` 原文「金孫現在聽得懂語音喔，您可以按住麥克風跟我說說話」在同一句裡先第三人稱自稱、再第一人稱說「跟我說」；`BIND_FIRST_PROMPT` 同類。最隱蔽的是 `reports/summaries.py`——`SUMMARY_PROMPT`、`_TRANSCRIPT_PROMPT` 與 `_ROLE_LABELS["assistant"]` 都寫「金孫」，模型照著把「金孫今天陪阿公聊了…」寫進**家屬直接讀的摘要正文**，改 strings 改不到。三處已改為阿白＋第一人稱，各補一條斷言（模式沿用 `test_agent.py` 既有的人設斷言），並更新一條把舊標籤寫死在期望值裡的既有測試。`binding/flow.py:30` 的 LINE 選單「您好，我是金孫」**刻意不改**：那是服務自我介紹，選單四項全是帳號管理動作，屬鐵律 8「金孫是服務名不可全域取代」的保留範圍。ruff 乾淨、後端 2563 passed／183 skipped。⏳ 未處理並待裁決：`strategies/reflection.py` 與 `safety/moderation.py`／`combined_classifier.py` 的內部提示詞仍稱「金孫」——前者產出的守則會注入 agent prompt，可能與「你是阿白」互相打架；後者是安全分類器，動提示詞需連 evals 一起跑，故不在本次範圍。 | 使用者 2026-08-09「要」 | S |

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
| v1.45 | 2026-08-09 | 辛-30 更新：W2 共用元件完成——Button 四 variant 暖黃膠囊、Field hint、Section inset、focus ring、新增 StatusPill 與 Chip；新元件同批接上 `SchedulesScreen` 與 `InviteCard`，不留未採用的元件。ui 測試 8→33 條，web 42 檔 675 條全過。 |
| v1.44 | 2026-08-09 | 辛-30 更新：W1 文案完成——`web/src/strings.ts` 30 處「金孫」逐條分類（21 處改阿白、10 處保留服務名），新增 `strings.test.ts` 30 條分兩組守門，連帶更新 7 支既有測試 27 處寫死的期望值。辛-31 更新：每晚反思 `strategies/reflection.py` 的提示詞與 `_ROLE_LABELS` 一併改阿白——它產出的守則會原文注入 agent 的 system prompt，兩份不同名會讓模型自稱失去保證；`safety/moderation.py` 與 `combined_classifier.py` 刻意不動（安全分類器，改提示詞需連 evals 一起跑）。 |
| v1.43 | 2026-08-09 | 新增辛-30：網頁版（`web/`）補齊新視覺六批，因發表要用網頁做 demo。第一步 token 已完成——`theme.css` 從 9 個色票擴到 17 色＋狀態態樣／舞台幾何／長輩端尺寸／動畫時長，`theme.test.ts` 改為直接比對 `app/src/lib/theme.ts` 原始碼，把「三端同值」從註解宣稱升格為測試把關。另補收六批範圍外的人設洩漏：`channels/inbound.py` 兩句長輩提示與 `reports/summaries.py` 摘要提示詞仍把角色叫「金孫」，已改為阿白＋第一人稱並各補一條斷言；`binding/flow.py` 的 LINE 選單「您好，我是金孫」刻意不改（那句是服務自我介紹，提供的也全是帳號管理動作）。 |
| v1.42 | 2026-08-08 | 辛-28 Android Expo Go 驗收：五 Tabs、中央 action、認證與返回、改回診／刪除真 API 往返、摘要空狀態及危急安全降級已實機通過；摘要有資料態與通知 badge 因遠端測試帳號無資料，改由既有自動化測試覆蓋。另修正登入／註冊在 SessionProvider 提交 session 前過早導向的競態，新增 2 條回歸測試。 |
| v1.41 | 2026-08-07 | 辛-28 更新：批次 6 真實契約版完成待人工驗收，新增純文字摘要、獨立改回診與危急詳情安全降級，4 支測試檔 6 條全綠；新增辛-29 追蹤摘要結構化、排程兩欄位、危急三端點、重新同意、稽核與 30 天刪除。 |
| v1.40 | 2026-08-07 | 辛-28 更新：批次 5 家屬端五項 Tabs、外層認證／深頁、中央 action、Android 返回、通知 badge 與第一位長輩集中規則完成；新增 9 條測試，批次 6 待後續指示。 |
| v1.39 | 2026-08-07 | 辛-28 更新：批次 4「之前聊過的」完成，新增 `/elder/history`、固定頁首與內容層捲動、最新在上、返回保證與 4 條畫面測試；依使用者選項 1，尚無真實音訊契約前不顯示「再聽一次」；批次 5～6 待逐批驗收。 |
| v1.38 | 2026-08-07 | 辛-28 更新：批次 3 對講機呈現層與真實「您說」完成，涵蓋固定舞台、一屏內容層規則、主鍵／回話卡動畫、第一段即展開、逐段收合、本機 todayLog 與後端 transcript；批次 4～6 待逐批驗收。 |
| v1.37 | 2026-08-07 | 辛-28 更新：批次 2 共用 UI 已完成，涵蓋五類元件、長輩端 big 尺寸、焦點相容調整與 8 條元件測試；批次 3～6 待逐批驗收。 |
| v1.36 | 2026-08-07 | 新增辛-28：KinSun 新視覺六批交接；批次 1 token／文案／人設／情緒黑名單與阿白離線 renderer 接縫完成，批次 2～6 待逐批驗收。 |
| v1.32 | 2026-08-01 | 辛-26 第二段完成（**F-17 結案**，T5，T4／T6 收尾後動工）：`location.ts::currentPlace` 恢復呼叫 `getCurrentPosition`＋`nearestCounty` 反查縣市名，座標仍送實際 GPS（模糊化後）；`useTalk.ts` 新增與 `probeMicrophone` 並列的獨立 mount effect 暖定位權限，`startRecording()` 既有呼叫不動。查證確認天氣／附近地點完全解除（後端只吃座標），路線恢復到與 App 版同等的行政區層級精度（非本輪退化）。新增 10 條測試、逐條變異驗證，web 573→**585** |
| v1.31 | 2026-08-01 | 辛-25 審查後補完四項（1 Critical＋1 Important＋2 Minor）：補播引入的續拉錯亂（舊答案開頭→新答案中段→新答案開頭）已修並更正「非本輪造成」那句錯誤自陳；字幕被新一輪搶走已修；解鎖守門補上 avatar 實況；17 摘要表補殘餘風險但書。再新增 5 條測試，web 573→**578** |
| v1.30 | 2026-08-01 | 新增辛-26（**F-17 第一段：縣市座標反查模組已備妥、尚未接線**，Leo 八項裁決第 6 項，⏳ 部分完成）：`web/src/elder/countyCoords.ts`（複製後端 `_COUNTY_COORDS`＋Haversine 最近鄰、120 公里門檻）與 `scripts/verify-county-coords.mjs`（防兩份表漂移，掛進 `npm run build`）；`location.ts`／`useTalk.ts` 刻意未接線（T4／T6 當時同支 `useTalk.ts` 收尾中，避免衝突延後）。新增 10 條測試、逐條變異驗證。web 563→**573** |
| v1.29 | 2026-08-01 | 新增辛-25（**對講機兩項裁決同時施工**，已完成）：①iOS 音訊解鎖提早到「播放器誕生後的第一個觸碰」（不再與開錄搶同一個音訊工作階段；查證後推翻「掛在配對畫面按鈕上」的直覺做法——那時播放器還不存在）；②插嘴後前一題的答案改為補播（推翻 2026-07-31 的「一律丟棄」，收音中不放音的保護未動；FIFO、上限 2 則）。新增 10 條測試、逐條變異驗證（一次推翻自己的預測、一次確認等價變異）。web 553→**563** |
| v1.28 | 2026-08-01 | 新增辛-24（**危急警報看起來像危急警報**，D-80，已完成）：`app_notifications` 加 `severity` 欄；前端橫幅與兩支清單畫面同步分級。T3 審查補完三項：長輩欄接線補對稱測試（刪掉那行原本 540 條全過）、認不得的 severity 由靜默降級改為 `console.warn` 留痕、對比度數字更正（6.47:1／2.70:1，原記的「過 AAA」不成立）。web 540→**553** |
| v1.27 | 2026-08-01 | 辛-23 審查後補完四項：F-19 結案（`web/` 顯示 `meta.warnings`）、`APPOINTMENT_REMINDER_HOUR` 補 0–23 範圍驗證（誤設原本回 500）、兩顆都過期的 400 訊息改講真正的原因、新增與編輯回傳不同的句子（編輯時前一天那顆可能已經送出過）。累計新增 27 條測試、36 次變異驗證全紅 |
| v1.26 | 2026-08-01 | 新增辛-23（修回診「前一天」提醒提早兩天響＋下午設明天的回診整筆建不起來，D-79，已完成）：推算改由後端接管（`timeparse.build_appointment_reminders`，REST 與 LINE 共用），REST 對 `kind=appointment`＋`event_date` 忽略 client 的 `occurrences`；已過期的「前一天」那顆改為略過而非讓整筆失敗，並不靜默（`meta.warnings`／LINE 回覆句）。兩件未處理：`meta.warnings` 四端未消費（F-19，待裁示）、凍結前端的顯示面根因未除（F-16）。新增 17 條測試、26 次變異驗證全紅 |
| v1.0 | 2026-07-08 | 初版：六批 40 工項＋里程碑；順序經 Leo 核准；分工待會-16 |
| v1.1 | 2026-07-09 | 會議決議回填：己批填入 8 個實際工項；分工＝Leo 單人（會-16）；乙-3／丁-3／丙-6 加 D-71／D-72 連動標註；彩排改暫定 |
| v1.2 | 2026-07-09 | D-71 三細節回填：乙-3 改 token 永久化（不做效期）；丁-3／己-6 解鎖 |
| v1.3 | 2026-07-10 | 戊批完工標記：CI 五 job＋覆蓋門檻 80%（現況 87%）、KPI 量測基建（token／往返 P50/P95／危急 P/R）全數落地 |
| v1.4 | 2026-07-12 | **新增庚批**：架構文檔深化（七群深潛）發現的 58 項後端＋8 項前端差距開成 56 個工項，分七區（立即修 HIGH 9／正確性 10／安全強化 7／前端 7／清理 13／待決策 3／範圍外文檔 7）；標註兩項深化中已解決（A-12 誤判、F-8 已補圖）。庚批未排入 8/20 時程，建議至少完成庚1 |
| v1.5 | 2026-07-12 | **內測基礎建設完工**（D-73，批次外插單，PR #45）：批①總開關＋meta＋.env 整理、批② App 雙 slot 快切、批③後台五分頁＋系統頁＋手動觸發；里程碑表補完工列 |
| v1.6 | 2026-07-12 | **新增辛批**（Leo 逐項指示的發表前功能補強）：辛-1 App 用藥回診編輯完成（App 12 頁，見 17 v1.6／12 v1.3） |
| v1.7 | 2026-07-13 | 庚批 56 項結案回填（追認補記——當時 commit 未同步版頭與本表） |
| v1.8 | 2026-07-17 | 辛批補記 7 工項並全數結案：辛-2 每晚反思、辛-3 web_search（7/14）、辛-4 自適應問候時間（7/16）、辛-5 長輩地點、辛-6 天氣正確性、辛-7 JS lint、辛-8 JS 測試基建（7/17）；標記庚-09 結案矛盾（55/56，待 Leo 確認） |
| v1.9 | 2026-07-17 | 新增辛-9 主動問候接續上次話題（讀「她上次開口那天」的摘要當檢索關鍵字＋注入＋任務加碼；否決 Mem0 昨晚整理項的理由見 spec）；一併修 Mem0 記憶日期晚一天；D-33「摘要無讀取端」現況自此失效（07 v1.3 同步） |
| v1.10 | 2026-07-18 | 己-7 補單庫 `--in-place` 遷移、寫入前 gzip＋SHA-256 備份與版本化個人庫驗收流程。 |
| v1.11 | 2026-07-18 | 己-7 實測回填：DISCOVERY 無回答向量、Gemini 批次 timeout／failed release 復用、舊 appointments schema 升級；個人庫 active 發布因 free-tier 每日 1,000 次 embedding 額度維持待驗收。 |
| v1.12 | 2026-07-18 | 己-7 結案：提高額度後完成 790 文件／2,808 chunks 的 active 發布、golden set 與結構閘門、Agent/Admin citation E2E、最小設定 RAG Worker 啟動驗收。 |
| v1.13 | 2026-07-25 | 新增辛-10 濫用審核（D-75）：三類越權攔截＋fail-open＋管線位置在家屬通報之後；evals 新增 careline-prompt-injection（32 題五類＋四項 GEval）。 |
| v1.14 | 2026-07-25 | 辛-10 開啟旗標：`SAFETY_MODERATION_ENABLED` 預設 true（Leo 核定），預設值由 `test_config` 釘死；並接入 promptfoo 紅隊（`evals/redteam/`，走 npx 不進專案依賴）。 |
| v1.15 | 2026-07-25 | 新增辛-11（觀測與評測強化五項，已完成）與辛-12（評測可信度防呆三項，未施工）；D-75 的實測數字全數作廢——LLM 裁判在配額耗盡時給出與自身理由矛盾的分數，旗標預設值待重跑後再定。 |
| v1.16 | 2026-07-26 | 新增辛-13 全流程模擬實測（106 場文字＋20 場真語音＋15 項瀏覽器點擊）：修好「每晚反思自 7/20 起全數失敗」與「/turns 佔住事件迴圈」兩項生產缺陷；另記錄危急誤報實際送達家屬、衛教回覆冒用政府機關名義等 4 嚴重／10 中等問題待拍板。 |
| v1.17 | 2026-07-26 | 新增辛-14 全流程模擬實測三項修復（危急症狀詞誤報、出站冒名防線、排程假死）：總測試 1808；`deploy/kinsun-scheduler.service` 已交付但尚未安裝。 |
| v1.19 | 2026-07-27 | 新增辛-17（工具回合思考層級，已完成，總測試 2047）：`gemini-3.5-flash-lite` 在未設 `thinking_config` 時工具形同不存在——Opik 對照 3.1 為 21/62、3.5 掉到 4/24，07-27 App 對話 0/7；改 MEDIUM 後原封重放 5/5，代價為每輪工具呼叫 +1.3 秒。 |
| v1.18 | 2026-07-27 | 新增辛-15（架構對比 ref/hermes-agent 後的六項邊界補強，已完成，總測試 1884）與辛-16（同報告的第二批 NEXT，未施工；其中兩項需前置查證或 Leo 表態） |
| v1.33 | 2026-07-30 |（Jerry 分支原 v1.26，2026-08-01 併入 main 時重編）將 Prototype 視覺工項改編為辛-27（分支上原編辛-23），與 main 已存在的辛-18 附近地點搜尋區分；同步整合 WebSocket 對講、提醒鈴鐺與 `POST /turns` 降級契約。 |
| v1.34 | 2026-07-30 |（Jerry 分支原 v1.27，2026-08-01 併入 main 時重編）辛-27 追加 main 同步後 WS 狀態收尾修正與回歸測試：ack 播完維持 thinking、reply 最後一段才 idle、error 不再顯示成待機，並阻止較舊播放回呼覆蓋新狀態。 |
| v1.35 | 2026-07-30 |（Jerry 分支原 v1.28，2026-08-01 併入 main 時重編）辛-27 補 TTS 純文字降級：WS reply 的 `audio_url=""` 時直接離開 thinking；有語音仍由播放完成事件收尾，新增 3 條回歸測試。 |
| v1.21 | 2026-07-28 | 新增辛-19（非同步工具調用與併發對話，P0～P3 全完成，spec `2026-07-28-非同步工具調用與並行對話-design.md`）：`WS /api/v1/ws/talk` 整輪長連線＋預錄安撫話語庫＋TTS 優先權佇列＋工具並行 dispatch＋併發輪四道安全。實測長輩聽到第一個字 9.50s→2.22s（省 7.28s／77%，n=6 真 Gemini＋正式庫＋真 TTS）。四支探針＋一支七代理調查推翻了設計初稿的三個前提：模型現在完全不吐安撫話（0/4，加提示詞後 4/4）、TTS 併發會塌且沒有規律（同一段落 1.88s vs 15.08s）、以及**模型的安撫話 65% 是一字不差的同一句罐頭話**——後者直接推翻「模型生成才貼合情境」的方案選擇，改為預錄語庫，連帶取消提示詞的 ACK_DIRECTIVE、`llm.py` 的改動與一整套八道出站防線。全庫測試 2258 passed，App 端 30 passed（tsc／eslint 全綠）。`app/src/app/elder/talk.tsx` 已改接 WebSocket，連線沒開時退回 `POST /turns`（降級路徑保留）。 |
| v1.24 | 2026-07-28 | 新增辛-22（修未註冊工具導致的退化輸出，已完成）：提示詞寫死點名的工具碰上條件式註冊，模型不會安靜跳過而是假裝呼叫、吐出 186,514 字的重複 `tool_code`，長輩實際是按完等三十秒沒聲音。修為出站護欄（工具語法偵測＋500 字上限）＋組裝時提示詞／註冊表對帳 warning；提示詞動態化（B）Leo 核定留待辦。修的是地雷不是當下故障——本機金鑰齊全故觸發不到。+13 測試。 |
| v1.23 | 2026-07-28 | 新增辛-21（一輪總時間預算，已完成）：逐次逾時攔不住一輪裡三次 Gemini 呼叫相加——Gemini 3.5 過載那晚長輩等了 96.6 秒才聽到回退話術。`turn_context` 新增 deadline contextvar，`llm.py` 兩個出口取 `min(逐次逾時, 本輪剩餘)`、用完直接拋不打出去，不新增降級分支（沿用三個呼叫端既有的 LLM 故障路徑）。預算含 ASR。歷史 68 輪 p95 19.8 秒佐證 30 秒砍不到正常對話。新增 13 條測試。 |
| v1.22 | 2026-07-28 | 新增辛-20（修對講機改走 WS 後定位失效，已完成）：App 端 `sendLocation` 把本地型別欄位名 `place` 直接送上線路，後端依契約讀 `location` 讀不到，`elder_locations` 自 17:51 起零筆寫入，金孫遂每次問地點都反問「您人在哪裡」（反問是設計、鍵名是 bug）。同步把 App 測試改成斷言線路鍵名——原本兩邊各自斷言自己那一版契約，全綠也擋不住。 |
| v1.20 | 2026-07-27 | 新增辛-18（附近地點搜尋，已完成）：`places` 表＋模組（Overture Maps 台灣 POI）＋ `search_nearby_places` 工具＋三道結果後處理（座標可疑剔除／去重／店名清洗）＋ `web_search` 職責收窄；順手修正 `locations/store.py` 檔頭與程式矛盾的敘述。人工真 LLM 驗證（真 Gemini＋正式庫）工具選擇 18/18 全對，追加發現並修復一個 Critical——模型把店名當 `place` 傳入被地理編碼照單全收（「麥當勞」→台南 254 公里），補距離護欄與中心點回傳。全庫測試 2137 passed。 |
