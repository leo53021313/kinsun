# API 設計規範 - 金孫 KinSun

> **版本:** v1.8 | **更新:** 2026-07-26 | **狀態:** ✅ 定稿（`GET /admin/jobs` 加逾期偵測欄位（`is_overdue`／`late_seconds`／`never_ran`／`meta.overdue`／`meta.never_ran`／`meta.warnings`）——`never_ran` 為 2026-07-26 補：沒有 `last_run_at` 就算不出 `due_at`、`is_overdue` 恆為 False，從沒被排程器碰過的 job 原本顯示成全綠；新增 `GET /turns/chunks/{index}` 分段語音串流＋三個錯誤碼，`POST /turns` 回應加 `chunk_count`／`reply_digest`；契約已拍板 D-23～D-29；/v1 已全面落地；`traces/{trace_id}` 回應加 `opik_url` 深連結）
> **基準:** as-is（現行 23 端點實證）＋ to-be（/v1 契約）。命名規則以 AGENTS.md 為準。
> DGX 服務認證與速率限制 → 13_安全循環；`admin api disabled` 503 措辭一併列 13。

---

## 1. 設計約定

| 項目 | 規範 | 依據 |
| :--- | :--- | :--- |
| 風格 | RESTful | — |
| Base URL | `/api/v1/`（App／LIFF 家屬面）；`/api/v1/admin/`（觀測後台） | ✅ D-27 |
| 格式 | `application/json`（UTF-8）；音檔上傳為 raw body、TTS 回應為 binary | — |
| 資源路徑 | 小寫、kebab-case、**複數名詞**（聚合計算端點可單數，如 `health-report`） | AGENTS.md |
| 欄位命名 | `snake_case`，request／response 同實體同鍵名，前後端（含 TS 型別）完全一致 | AGENTS.md |
| 時間戳 | `<動詞過去分詞>_at`，**epoch 秒（DOUBLE PRECISION）**——刻意不採模板的 ISO 8601，維持 AGENTS.md 既有規範 | AGENTS.md |
| 認證 | Bearer Token（`Authorization` header）；三機制見 §4 | — |
| 版本控制 | URL 路徑 `/v1/`；破壞性變更需開新版本 | ✅ D-27 |
| 路由組織 | `web/routers/` 套件，**一資源一檔**；prefix 由組裝處（app.py）統一指定，router 檔內不硬寫；OpenAPI tags 分群 | ✅ D-28 |

---

## 2. 通用行為

### 2.1 統一信封（✅ D-23）

除豁免清單（§2.4）外，所有端點回應一律：

```json
// 成功
{ "success": true,  "data": { ... }, "error": null, "meta": null }
// 成功（列表＋分頁）
{ "success": true,  "data": [ ... ], "error": null,
  "meta": { "limit": 100, "before": 1720000000.0, "after": null, "has_more": true } }
// 失敗
{ "success": false, "data": null,
  "error": { "code": "invalid_token", "message": "登入憑證無效，請重新登入" }, "meta": null }
```

- `error.code`＝標準錯誤碼（§3），機器判斷用；`error.message`＝繁中人話，UI 直接顯示。
- 列表不再用命名鍵包陣列（`{"medications":[...]}` → `data` 陣列）；三個前端解包點同步改。

### 2.2 分頁（✅ D-29）

游標分頁：`limit`（預設 100、上限 500）＋ `after`（取更新）／`before`（回翻歷史），游標值＝`created_at` epoch 秒。適用 `/api/v1/admin/messages`；家屬面列表（長輩／用藥／回診）資料量小，**不分頁**（明文豁免）。

### 2.3 驗證錯誤統一（✅ D-24）

攔截 FastAPI `RequestValidationError`，改寫為信封格式：`error.code="validation_error"`，`error.message` 取第一個欄位錯誤的人話描述，`meta.fields` 附逐欄位明細。手寫驗證同樣走標準錯誤碼（`name_required`、`invalid_date`…），**不再回自由字串**。

### 2.4 信封豁免清單

| 端點 | 理由 |
| :--- | :--- |
| `DELETE`（204） | 無 body，維持 204 |
| `POST /synthesize`（TTS） | binary 回應（`audio/mp4`＋`X-Duration-Ms`） |
| `POST /line/webhook` | LINE 平台契約，維持 `{"ok": true}` |
| `GET /healthz`（ASR／TTS） | 監控探針慣例 |

### 2.5 冪等性／速率限制

as-is 皆無。速率限制 → 13 循環議；`Idempotency-Key` 現階段 YAGNI（單一自有客戶端），若開放第三方再議。

---

## 3. 錯誤處理（✅ D-24）

### 標準錯誤碼清單

| 錯誤碼 | HTTP | 語意 |
| :--- | :---: | :--- |
| `missing_token` | 401 | 未帶 Authorization |
| `missing_token` | 401 | 未帶 Authorization header |
| `invalid_token` | 401 | token 無效／型別不符（取代 as-is 的 `"invalid token"`／`"missing bearer token"`） |
| ~~`token_expired`~~ | — | **作廢**（D-25 修訂：全 token 永久記住，無過期） |
| `invalid_credentials` | 401 | 帳密錯誤（不洩露帳號存在性，維持現行良好實務） |
| `invalid_admin_key` | 401 | admin 金鑰錯誤 |
| `consent_revoked` | 403 | 同意已撤回 |
| `elder_not_found`／`medication_not_found`／`appointment_not_found`／`trace_not_found`／`invite_not_found` | 404 | 資源不存在（`not_found` 細分化） |
| `email_taken` | 409 | 註冊 email 已存在 |
| `phone_taken` | 409 | 手機號碼已綁另一位長輩（己-6） |
| `invalid_phone` | 409 | 手機號碼格式不正確（己-6） |
| `password_too_short` | 409 | 密碼不足 8 字元（服務層驗證，✅ 庚-20） |
| `not_paired` | 409 | 長輩帳密登入但未掃碼配對（己-6：首次一定掃碼） |
| `invite_used`／`invite_expired`／`too_many_attempts`／`invite_wrong_role` | 409 | 邀請碼狀態錯誤（wrong_role＝家屬碼誤走裝置綁定，✅ 庚-04） |
| `name_required`／`label_required`／`slots_required`／`invalid_slot`／`invalid_date`／`invalid_time`／`date_in_past` | 400 | 欄位業務驗證失敗 |
| `invalid_status`／`invalid_action` | 400 | admin 守則：查詢狀態不在白名單／動作非 `revoke`（後台不提供採用，守則自動生效） |
| `strategy_not_found` | 404 | admin 守則：查無此守則，或它已不在生效中（撤銷是條件式 `UPDATE ... RETURNING`，撤不到即回本錯誤——不先查後撤，避免謊報「已撤銷」） |
| `validation_error` | 422 | pydantic 欄位驗證失敗（統一改寫，§2.3） |
| `audio_too_large` | 413 | 音檔超過上限（上限值 env 可調，✅ D-26） |
| `unsupported_media_type` | 415 | 對講機收到非音訊 content-type（✅ D-61 丙-11） |
| `too_many_requests` | 429 | 認證節流（✅ D-20 甲-3；跨進程共享，✅ 庚-08） |
| `job_not_found` | 404 | admin 手動觸發：查無此排程任務（spec 2026-07-12） |
| `chunk_not_found` | 404 | 分段語音：這位長輩今天還沒有回覆，或 index 超出段數（2026-07-26） |
| `chunk_superseded` | 409 | 分段語音：那一輪已被新的一輪取代，前端應停止續播（2026-07-26） |
| `speech_unavailable` | 502／503 | 分段語音：合成或上傳失敗、或伺服器未接語音相依（2026-07-26） |
| `internal_testing_disabled` | 403 | admin 手動觸發：內測模式未開（`INTERNAL_TESTING_ENABLED=false`，spec 2026-07-12） |
| `admin_disabled` | 503 | admin 未設金鑰（fail-closed；措辭是否洩組態 → 13 循環） |
| `overloaded` | 503 | ⚠️ 死碼待清（庚-43）：文案表殘留、無拋出點 |

> **中央註冊（✅ 庚-25）**：以上錯誤碼的唯一出處為 `src/kinsun/web/errors.py` 的 `ErrorCode`；
> `tests/test_web_errors.py` 強制「每碼必有繁中文案、文案表無孤兒」雙向對齊。新增錯誤碼三步見該模組 docstring。

---

## 4. 認證與 Token 生命週期

| 機制 | 適用 | as-is | to-be（✅ D-25） |
| :--- | :--- | :--- | :--- |
| App Bearer token（家屬） | `/api/v1/` 家屬面 | `token_urlsafe(32)`，SHA-256 雜湊存放；**永久有效、無登出** | 加 `expires_at`＋`DELETE /api/v1/sessions`（登出撤銷）；過期回 `token_expired` |
| App Bearer token（長輩裝置） | `POST /api/v1/turns` | 永久有效；每回合仍以閘門複核同意（撤回即 403） | **維持長效**；家屬端可作廢重綁（撤銷舊裝置 token＋重發綁定碼） |
| LIFF idToken | `/api/v1/` 家屬面（過渡） | 每請求即時打 LINE verify | 維持（隨 LINE 凍結，退場時移除，ADR-009） |
| `X-Admin-Key` | `/api/v1/admin/` | 靜態共用金鑰，`hmac.compare_digest` | 維持；輪替機制 → 13 循環 |
| DGX 服務 | `/transcribe`／`/synthesize` | **無認證** | → 13 循環議 |

---

## 5. 端點定義（as-is → to-be 路徑對照）

> ⚠ **D-28 備註**：依「routers 資源化」決議，to-be 擬移除 `app` 路徑段（資源本身已表達語意，通道由 token 型別判別）。此推導已於決策清單標註，可否決。

### 家屬面（tags: guardians／elders／schedules／reports）

| as-is | to-be | 說明 |
| :--- | :--- | :--- |
| `GET /api/me/elders` | `GET /api/v1/elders` | 列登入家屬管理的長輩（✅ D-28 改名） |
| `POST /api/elders` | `POST /api/v1/elders` | 建長輩＋首綁邀請碼；payload `{name, nickname?}`（✅ 庚-29——LIFF 家屬名改由後端取 ID token 顯示名稱，前端不再自送 guardian_name；nickname＝稱謂選填 ≤50 字，2026-07-17）；列表與建立回應皆含 `nickname` |
| —（新增） | `PUT /api/v1/elders/{elder_id}/profile` | 家屬補設／更改稱謂（2026-07-17）：payload `{nickname}`（≤50 字，空字串＝清除）；PUT＝upsert；未管理 404 |
| `POST /api/elders/{elder_id}/guardian-invites` | `POST /api/v1/elders/{elder_id}/guardian-invites` | 產家屬邀請碼 |
| —（D-76 P3 取代） | `GET|POST /api/v1/elders/{elder_id}/schedules`、`PUT|DELETE .../{group_id}` | 統一排程 CRUD；payload `{kind, title, occurrences[], event_date?, event_time?}`，操作單位為 group |
| `GET /api/elders/{elder_id}/health-report` | `GET /api/v1/elders/{elder_id}/health-report` | 聚合單數（規範允許）；✅ D-09 已新增 `GET /api/v1/elders/{elder_id}/daily-summaries`（己-3，2026-07-10：列表資源、`limit` 1–90 預設 30、meta 帶 limit）；`?window_days=1..90` 選填、預設 30（✅ 庚-40） |
| — | `DELETE /api/v1/sessions` | **新增**：登出（撤銷當前 token，D-25）；家屬與長輩 token 皆可（✅ 庚-42 長輩自助登出） |
| — | `DELETE /api/v1/sessions/all` | **新增**：登出所有裝置（撤銷該家屬全部 token，庚-05／A-47，2026-07-12） |
| — | `DELETE /api/v1/elders/{elder_id}/device-bindings` | **新增**：作廢長輩裝置重綁（D-25） |

### App 帳號與對講機（tags: auth／turns）

| as-is | to-be | 說明 |
| :--- | :--- | :--- |
| `POST /api/app/guardians` | `POST /api/v1/guardians` | 家屬註冊 |
| `POST /api/app/sessions` | `POST /api/v1/sessions` | 登入 |
| `POST /api/app/device-bindings` | `POST /api/v1/device-bindings` | 長輩裝置綁定（PROXY 同意留痕；首次配對必經；僅收長輩綁定碼——家屬邀請碼回 409 invite_wrong_role，庚-04／A-46，2026-07-12） |
| —（新增） | `PUT /api/v1/elders/{elder_id}/account` | ✅ D-71（己-6）：家屬代辦長輩帳密（帳號＝手機號碼；PUT＝重設）；invalid_phone 400／phone_taken 409 |
| —（新增） | `POST /api/v1/elder-sessions` | ✅ D-71（己-6）：長輩帳密登入（只管重登；未配對 403 not_paired）；納 D-58 節流 |
| —（新增） | `GET /api/v1/turns/chunks/{index}` | **分段語音串流**（2026-07-26 延遲優化）：取本輪回覆的第 index 段語音。長輩 Bearer token 認證；query `digest`＝`POST /turns` 回應裡的 `reply_digest`，不符即 409（那輪已被新的一輪取代，前端應停止續播）。回覆全文取自這位長輩**自己**今天最後一則金孫回覆（`turns` 表），故不另建表、也沒有「任意文字丟進來合成」的濫用面。回應：`{audio_url, duration_ms, text}` |
| `POST /api/app/turns` | `POST /api/v1/turns` | 對講機回合（raw body 音檔；上限 env 化 D-26）。回應自 2026-07-26 起多兩個欄位：`chunk_count`（整段回覆被切成幾段；>1 代表 `audio_url` 只是**第一段**，其餘用 `GET /turns/chunks/{index}` 依序取）與 `reply_digest`（取後續段落時帶上）。分段只對 App 通道啟用——LINE 一輪只能回一則語音，給它第一句等於把後面的話吞掉。選填 query：`location`＋`latitude`＋`longitude`（長輩地名＋模糊座標，App 端已四捨五入至 0.01 度；**三者齊備才寫入** `elder_locations`，寫入排在 dispatch 之前，缺任一即忽略、不清空既有值——spec 2026-07-17 長輩目前地點） |
| `current_app_guardian` 屬性 | **刪除** | 死碼（D-28） |

### 觀測後台（tags: admin）

| as-is | to-be | 說明 |
| :--- | :--- | :--- |
| `GET /api/admin/overview`／`elders`／`messages`／`elders/{elder_id}/timeline`／`traces/{trace_id}` | 同路徑掛 `/api/v1/admin/` | messages 加 `before` 回翻（D-29）；`traces/{trace_id}` 回應加 `opik_url`（工程觀測開啟且捕捉到 Opik trace id 時＝直達 Opik 的深連結，否則空字串，前端據此隱藏連結）|
| —（新增） | `GET /api/v1/admin/elders/{elder_id}/reminders`／`memory`／`account`／`risk-notifications`、`GET /api/v1/admin/jobs` | 內測基礎建設（spec 2026-07-12）：長輩詳情四分頁＋排程狀態，唯讀、`X-Admin-Key` 守門 |
| —（加欄位） | `GET /api/v1/admin/jobs` | 逾期偵測（2026-07-26 全流程模擬實測）：每列加 `due_at`／`late_seconds`／`is_overdue`，`meta` 加 `overdue`（逾期的 job 名陣列）與 `warnings`（人話告警）。判定＝`croniter(cron, last_run).get_next()` 早於現在超過 5 分鐘；`last_run_at` 為 null（從未跑過）者不判逾期。**加法**，舊前端忽略即維持原行為 |
| `/elders/{id}/medications`、`/elders/{id}/appointments`（**移除**） | `GET/POST/PUT/DELETE /api/v1/elders/{elder_id}/schedules[/{group_id}]` | 統一排程（D-76 P3）：用藥、回診與長輩自訂三類合成單一資源。**操作單位為 group（一件事）而非單一鬧鐘**——家屬按刪除時想刪的是「這個藥」，不是「這個藥的早上那次」。`kind` query 可篩類型；PUT 走 replace_group（先驗證再動手，失敗時原組原封不動）；DELETE 為軟刪（寫 `cancelled_at`，永久保留）。 |
| `POST .../reminders/dispatch`（body 改） | 同路徑，body 由 `{kind, slot}` 改為 `{kind}`（medication／appointment／custom） | 改接統一派送（D-76 P5）。⚠ 手動觸發**不寫** `fired_at`／`settled_at`——測試動作不可吃掉長輩當天真正該收到的那一則。 |
| `GET .../admin/elders/{id}/reminders`（回應改） | 同路徑，`medications`＋`appointments` 兩份清單合成 `schedules` 一份 | kind 欄位保留分類，另有 `created_by` 區分家屬設的與長輩自己交代的。 |
| —（新增） | `POST /api/v1/admin/jobs/{job_name}/run`、`POST /api/v1/admin/elders/{elder_id}/reminders/dispatch` | 內測手動觸發（spec 2026-07-12）：需 `X-Admin-Key`＋`INTERNAL_TESTING_ENABLED=true`（否則 403 `internal_testing_disabled`）；RPC 動作式路徑為 admin 內部工具刻意例外；不寫 `scheduler_state` |
| —（新增） | `GET /api/v1/meta` | 公開端點（無認證）：回 `{internal_testing: bool}` 供 App／admin 前端決定內測功能顯示（spec 2026-07-12） |
| —（新增） | `GET /api/v1/admin/news?days=3`（1–30） | 話題新聞檢視（D-74 消費端，2026-07-25）：回近 N 天爬到的新聞（news_item_id／source_id／title／url／publisher／published_at／retrieved_at，`meta` 帶 days＋count；content 刻意不回——列表要輕，原文點 url），唯讀、`X-Admin-Key` 守門 |
| —（新增） | `GET /api/v1/admin/strategies?status=adopted`、`PATCH /api/v1/admin/strategies/{strategy_id}` | 守則檢視與撤銷（每晚反思）：守則自動生效、無待審佇列，故 PATCH 只收 `{"action": "revoke"}`（其餘 400 `invalid_action`），**不提供採用**；`status` 須為 `adopted`／`revoked`／`superseded`（否則 400 `invalid_status`）；撤不到生效中的守則回 404 `strategy_not_found`。列表回傳含 `evidence`／`observed_days`（僅後台可見，不進 system prompt） |

### 平台契約（不入信封、不入 v1）

`POST /line/webhook`（HMAC 驗簽）；DGX `POST /transcribe`、`POST /synthesize`、`GET /healthz`（加 body 上限＋請求驗證，D-26）。

---

## 6. 資料模型（核心 JSON 形狀，snake_case）

```json
// Elder：{ "elder_id": "uuid", "name": "string" }
// Medication：{ "medication_id": "uuid", "name": "string", "slots": ["morning|noon|evening|bedtime"] }
// Appointment：{ "appointment_id": "uuid", "date": "YYYY-MM-DD", "label": "string" }
// Turn 回應 data：{ "text": "string", "audio_url": "string|null", "duration_ms": 1234 }
// 認證回應 data：{ "guardian_id|elder_id": "uuid", "name": "string", "token": "string(僅此一次)" }
//                  // D-25 2026-07-09 修訂：token 一律永久有效（登入一次永久記住），expires_at 取消
// 健康報告 data：{ "risk_events": [{"tier": 2, "reason": "...", "created_at": 0.0}],
//                  "reminders": [{"kind": "...", "content": "...", "created_at": 0.0}] }  // ✅ D-09 維持＋另開每日摘要端點（己-3）；tier 上限隨 D-72 改三級
```

---

## 7. 差距與重構項（餵 16_WBS）

| # | 工項 | 依據 | 影響面 |
| :--- | :--- | :--- | :--- |
| API-1 | `/api/v1` 前綴遷移＋信封導入（後端全端點） | D-23、D-27 | **破壞性**：app/src/lib/api.ts、frontend/src/api.ts、frontend/src/admin/api.ts 三處解包與路徑同步改 |
| API-2 | 標準錯誤碼落地＋RequestValidationError 統一 | D-24 | 全 handler＋前端錯誤顯示 |
| API-3 | 家屬 token 效期＋登出；長輩裝置作廢重綁；`api_tokens.expires_at` | D-25 | accounts、App 登入流、DB migration |
| API-4 | 上限 env 化＋DGX 服務請求驗證與 body 上限 | D-26 | turns、services/asr、services/tts |
| API-5 | `web/routers/` 套件重組＋prefix 上移＋tags＋刪死碼＋`GET /v1/elders` 改名 | D-28 | web/ 全域、app.py 組裝 |
| API-6 | admin messages `before` 游標＋信封 meta | D-29 | admin_api＋admin 前端 |

## 變更紀錄

| 版本 | 日期 | 變更 |
| :--- | :--- | :--- |
| v1.0 | 2026-07-08 | 初版：D-23～D-29 契約定稿 |
| v1.1 | 2026-07-17 | turns 補位置三參數（location／latitude／longitude 模糊座標，三者齊備才寫入）；追認 7/12–7/14 已回填而未升版的內容（sessions/all、内測端點、守則端點、錯誤碼中央註冊等） |
| v1.2 | 2026-07-17 | 稱謂欄位（elders.nickname）：POST /elders 收選填 nickname、GET /elders 回傳 nickname、新增 PUT /elders/{elder_id}/profile 補設稱謂 |
| v1.4 | 2026-07-25 | 新增 `GET /api/v1/admin/news`（話題新聞檢視，D-74 消費端）。 |
