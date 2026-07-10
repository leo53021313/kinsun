# API 設計規範 - 金孫 KinSun

> **版本:** v1.0 | **更新:** 2026-07-08 | **狀態:** ✅ 定稿（契約已拍板 D-23～D-29，程式碼落地列 16_WBS）
> **基準:** as-is（現行 22 端點實證）＋ to-be（/v1 契約）。命名規則以 AGENTS.md 為準。
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
| `invalid_token` | 401 | token 無效／型別不符（取代 as-is 的 `"invalid token"`／`"missing bearer token"`） |
| `token_expired` | 401 | 家屬 token 過期（D-25 新增） |
| `invalid_credentials` | 401 | 帳密錯誤（不洩露帳號存在性，維持現行良好實務） |
| `invalid_admin_key` | 401 | admin 金鑰錯誤 |
| `consent_revoked` | 403 | 同意已撤回 |
| `elder_not_found`／`medication_not_found`／`appointment_not_found`／`trace_not_found`／`invite_not_found` | 404 | 資源不存在（`not_found` 細分化） |
| `email_taken` | 409 | 註冊 email 已存在 |
| `invite_used`／`invite_expired`／`too_many_attempts` | 409 | 邀請碼狀態錯誤 |
| `name_required`／`label_required`／`slots_required`／`invalid_slot`／`invalid_date`／`date_in_past` | 400 | 欄位業務驗證失敗 |
| `validation_error` | 422 | pydantic 欄位驗證失敗（統一改寫，§2.3） |
| `audio_too_large` | 413 | 音檔超過上限（上限值 env 可調，✅ D-26） |
| `invalid_signature` | 400 | LINE webhook 驗簽失敗 |
| `admin_disabled` | 503 | admin 未設金鑰（fail-closed；措辭是否洩組態 → 13 循環） |
| `overloaded` | 503 | DGX 服務過載（信號量滿） |

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

### 家屬面（tags: guardians／elders／medications／appointments／reports）

| as-is | to-be | 說明 |
| :--- | :--- | :--- |
| `GET /api/me/elders` | `GET /api/v1/elders` | 列登入家屬管理的長輩（✅ D-28 改名） |
| `POST /api/elders` | `POST /api/v1/elders` | 建長輩＋首綁邀請碼 |
| `POST /api/elders/{elder_id}/guardian-invites` | `POST /api/v1/elders/{elder_id}/guardian-invites` | 產家屬邀請碼 |
| `GET|POST /api/elders/{elder_id}/medications`、`PUT|DELETE .../{medication_id}` | 同路徑掛 `/api/v1/` | 用藥 CRUD |
| `GET|POST /api/elders/{elder_id}/appointments`、`PUT|DELETE .../{appointment_id}` | 同路徑掛 `/api/v1/` | 回診 CRUD |
| `GET /api/elders/{elder_id}/health-report` | `GET /api/v1/elders/{elder_id}/health-report` | 聚合單數（規範允許）；✅ D-09 已新增 `GET /api/v1/elders/{elder_id}/daily-summaries`（己-3，2026-07-10：列表資源、`limit` 1–90 預設 30、meta 帶 limit） |
| — | `DELETE /api/v1/sessions` | **新增**：登出（D-25） |
| — | `DELETE /api/v1/elders/{elder_id}/device-bindings` | **新增**：作廢長輩裝置重綁（D-25） |

### App 帳號與對講機（tags: auth／turns）

| as-is | to-be | 說明 |
| :--- | :--- | :--- |
| `POST /api/app/guardians` | `POST /api/v1/guardians` | 家屬註冊 |
| `POST /api/app/sessions` | `POST /api/v1/sessions` | 登入 |
| `POST /api/app/device-bindings` | `POST /api/v1/device-bindings` | 長輩裝置綁定（PROXY 同意留痕；首次配對必經） |
| —（新增） | `PUT /api/v1/elders/{elder_id}/account` | ✅ D-71（己-6）：家屬代辦長輩帳密（帳號＝手機號碼；PUT＝重設）；invalid_phone 400／phone_taken 409 |
| —（新增） | `POST /api/v1/elder-sessions` | ✅ D-71（己-6）：長輩帳密登入（只管重登；未配對 403 not_paired）；納 D-58 節流 |
| `POST /api/app/turns` | `POST /api/v1/turns` | 對講機回合（raw body 音檔；上限 env 化 D-26） |
| `current_app_guardian` 屬性 | **刪除** | 死碼（D-28） |

### 觀測後台（tags: admin）

| as-is | to-be | 說明 |
| :--- | :--- | :--- |
| `GET /api/admin/overview`／`elders`／`messages`／`elders/{elder_id}/timeline`／`traces/{trace_id}` | 同路徑掛 `/api/v1/admin/` | messages 加 `before` 回翻（D-29） |

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
