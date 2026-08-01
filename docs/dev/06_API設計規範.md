# API 設計規範 - 金孫 KinSun

> **版本:** v1.24 | **更新:** 2026-08-01 | **狀態:** ✅ 定稿（**容量上限核定後更正 `queued` 說明的舉例**（2026-08-01）：`TURN_CONCURRENCY_LIMIT` 由暫定 6 核定為 **2（每 worker，全域＝×`WEB_WORKERS`）**，原文以「預設 6」舉例說明「排隊名次 ≠ 前面還有幾位」，已同步改為 2；**網頁版前端 P3 對講機容量閘門接線**（Task 2）：`WS /ws/talk` 下行新增 `queued` 訊框告知排隊位置；`POST /turns` 超限（含排隊逾時）改回 503 `too_many_requests`（與認證節流 429 同碼不同狀態碼）；兩條路徑另加每位長輩每分鐘 30 輪節流保險絲；`GET /api/v1/demo-status` 補 single-flight 與探針齊全性 fail-fast（P1 全分支審查 I5／I6）；新增 `GET /api/v1/demo-status`（網頁版前端 P1 地基，任務 12）：公開免認證、回應形狀 `{overall, components}`、結果快取 5 秒；**`WS /api/v1/ws/talk` 回覆音檔改隨 binary 訊框直送**（2026-07-30 延遲優化 C1）：自我描述訊框（長度前綴＋JSON header＋m4a bytes），省掉「上傳 Supabase→App 再下載」兩趟網路；header 嵌在同一訊框是因為併發輪的訊框交錯會讓順序配對錯位；兩處無界輸入補上限：排程名稱 50 字（A-06，35 萬字實測讓清單回應膨脹到 1 MB／16.7 秒）、地名 100 字（V-05，2 萬字會每輪注入提示詞）；422 欄位明細不再外洩 pydantic 原文與正規表示式，改為 `{field, code, message}`（A-05）；`POST /guardians` 的全空白名稱改與 `/elders` 同調（A-07）；錯誤契約四修：框架層 404／405 補 `not_found`／`method_not_allowed`（A-04）、排程驗證改 `invalid_schedule`＋繁中 message（A-01）、沒帶憑證統一回 `missing_token`（A-08）、`shared` 的 Elder 型別補 `nickname`（A-10）；邊界輸入三修：`Authorization` scheme 大小寫不敏感（A-15）、邀請碼剝前後空白（A-11）、`PUT /schedules` 改 kind 由靜默忽略改為 400 `kind_not_changeable`（A-09）；位置座標補範圍驗證（V-04）：WS 與 REST 兩條路徑共用 `locations.is_valid_coordinate`，REST 刻意忽略而非 422（422 會連長輩那句話一起退掉）；`WS /api/v1/ws/talk` 位置訊框補欄位型別把關（V-03）——型別錯會砍斷整條連線且不送 error 訊框，且發作在長輩下一次開口時；新增 `POST/DELETE /api/v1/push-tokens` 裝置推播 token 註冊（真推播 D-08 階段 5）——主體由 Authorization 決定不由呼叫端宣告；新增 `GET /api/v1/elder-notifications` 長輩讀自己的 App 內通知（X-01，2026-07-29 全面自動化測試）——提醒送出後只有家屬讀得到、且只查家屬自己的 `external_id`，寫給長輩的那一列誰都讀不到，用藥／回診／主動關懷對純 App 家庭等於不存在；真推播 D-08 階段 5 到位後本端點仍是補拉路徑；新增 `WS /api/v1/ws/talk` 對講機長連線（非同步工具調用，spec 2026-07-28）——整輪走同一條連線讓「算出答案的 worker 推不到長輩的連線」這個問題自動消失，`POST /turns` 保留為降級路徑；`GET /admin/jobs` **母體改為全系統排程宣告**（`cron/registry.py`，含跑在 RAG Worker 程序的 `rag-weekly-refresh`）並加 `owner`／`can_run_now` 兩欄，手動觸發對本程序跑不了的排程回 409 `job_not_runnable_here`——原本這一頁只看得到 webhook 程序綁得出來的 job，RAG 週更停擺或從未執行一律顯示全綠；`GET /admin/jobs` 加逾期偵測欄位（`is_overdue`／`late_seconds`／`due_at`／`never_ran`／`meta.overdue`／`meta.never_ran`／`meta.warnings`），**逾期容許量改逐 job**（`schedule-dispatch` 用自己的 90 秒判定窗，預設仍 300 秒）——`never_ran` 為 2026-07-26 補：沒有 `last_run_at` 就算不出 `due_at`、`is_overdue` 恆為 False，從沒被排程器碰過的 job 原本顯示成全綠；新增 `GET /turns/chunks/{index}` 分段語音串流＋三個錯誤碼，`POST /turns` 回應加 `chunk_count`／`reply_digest`；契約已拍板 D-23～D-29；/v1 已全面落地；`traces/{trace_id}` 回應加 `opik_url` 深連結）
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

攔截 FastAPI `RequestValidationError`，改寫為信封格式：`error.code="validation_error"`，`meta.fields` 附逐欄位明細，每筆為 `{field, code, message}`。手寫驗證同樣走標準錯誤碼（`name_required`、`invalid_date`…），**不再回自由字串**。

> ⚠️ **`meta.fields[].message` 絕不回 pydantic 原文**（A-05，2026-07-29）：它是英文散文，而且會把驗證用的正規表示式原樣吐出去（實測 `"String should match pattern '^[^@]+@[^@]+\\.[^@]+$'"`）——那串 pattern 是實作細節，對呼叫端沒有用，卻等於把驗證規則公開。改為 `code`＝pydantic 的機器可讀 `type`（`string_too_short`／`int_parsing`…）供程式分支、`message`＝繁中人話供顯示；沒對應到的型別退回**泛用繁中**而非英文原文（退回原文等於這道防線在遇到沒見過的錯時自動失效）。

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
| `missing_token` | 401 | **完全沒帶憑證**（無 Authorization 或剝掉 scheme 後為空）。⚠️ 與 `invalid_token` 的分野對 UI 是實質的：前者是「還沒登入」該導去登入頁，後者是「登入失效」該清掉 session 再導。原本全庫只有家屬雙認證回這個碼、其餘九支端點一律回 `invalid_token`，App 的 401 統一處理只能猜（A-08，2026-07-29） |
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
| `name_required` | 400 | 名稱為空或**全空白**。⚠️ `POST /guardians` 原本只驗 `min_length=1`，三個空白照收，那位家屬在 UI 上永遠是一片空白且無人提醒——與 `POST /elders` 早已 strip 後擋下的行為不同調（A-07，2026-07-29）。兩支現在都是 strip 後判空，存入的名稱也一律去頭尾空白 |
| `name_required`／`label_required`／`slots_required`／`invalid_slot`／`invalid_date`／`invalid_time`／`date_in_past` | 400 | 欄位業務驗證失敗 |
| `not_found`／`method_not_allowed` | 404／405 | **框架層**（打錯網址、方法不對）的統一出口。原本 FastAPI 自己丟的 `detail` 是英文句子「Not Found」，會被原封當成 `error.code`——那是給機器判斷用的欄位，英文句子等於前端無從分支，而 `message` 又因查無文案退回碼本身，於是使用者也看到英文（A-04，2026-07-29） |
| `invalid_schedule` | 400 | 排程業務驗證失敗（時間已過去、太遠、事情太多、**名稱超過 50 字**…）。`error.message` 帶服務層寫好的繁中人話——那些句子是寫給長輩看的，LINE 流程與 LLM工具都直接用；原本整句被塞進 `error.code`（A-01，2026-07-29） |
| `kind_not_changeable` | 400 | `PUT /schedules/{group_id}` 送了與原本不同的 `kind`。**類型不可改是刻意的**（`replace_group` 沿用原 kind：改內容不該讓家屬設的藥變成長輩設的、用藥變成回診），要換類型得刪掉重建。原本是收下必填的 `kind` 卻靜默忽略——家屬改分類拿到 200 與一筆沒變的資料，UI 沒有理由懷疑它（A-09，2026-07-29） |
| `invalid_status`／`invalid_action` | 400 | admin 守則：查詢狀態不在白名單／動作非 `revoke`（後台不提供採用，守則自動生效） |
| `strategy_not_found` | 404 | admin 守則：查無此守則，或它已不在生效中（撤銷是條件式 `UPDATE ... RETURNING`，撤不到即回本錯誤——不先查後撤，避免謊報「已撤銷」） |
| `validation_error` | 422 | pydantic 欄位驗證失敗（統一改寫，§2.3） |
| `audio_too_large` | 413 | 音檔超過上限（上限值 env 可調，✅ D-26） |
| `unsupported_media_type` | 415 | 對講機收到非音訊 content-type（✅ D-61 丙-11） |
| `too_many_requests` | 429 | 認證節流（✅ D-20 甲-3；跨進程共享，✅ 庚-08）；對講機每位長輩每分鐘輪數保險絲（P3 Task 2，2026-07-31） |
| `too_many_requests` | 503 | ⚠️ 同碼不同狀態碼：對講機容量閘門（`TurnAdmission`）排隊逾時（P3 Task 2，2026-07-31）——語意是「伺服器容量暫時不足，稍後會恢復」而非「你打太快」，故意不與上列 429 共用狀態碼；`error.message` 帶服務層寫好的婉拒人話，與 WS `queued`／`error` 路徑同一句 |
| `job_not_found` | 404 | admin 手動觸發：查無此排程任務（spec 2026-07-12） |
| `job_not_runnable_here` | 409 | admin 手動觸發：這支排程存在，但由別的程序執行（如 `rag-weekly-refresh` 住在 rag_worker），後台無法就地觸發。與 404 分開是刻意的——「按不動」與「查無此 job」混成同一個碼，值班的人會以為後台壞了 |
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

> ⚠️ **`Authorization` 的 scheme 大小寫不敏感**（RFC 7235）：`bearer`／`BEARER` 一律認得，單一出處為 `web/routers/deps.strip_bearer`。原本各處寫 `removeprefix("Bearer ")`，小寫進來剝不掉、token 變成 `"bearer xxx"` → 401 `invalid_token`——**症狀跟 token 失效一模一樣**，呼叫端會去查 token 生命週期而不是查大小寫（A-15，2026-07-29）。同檔的 `current_guardian` 早就用 `scheme.lower()` 做對了，其餘幾支沒有：那是漂移不是設計。
>
> ⚠️ **邀請碼前後空白一律剝掉**（`redeem_invite`／`preview_invite`，涵蓋 App 綁定與 LINE 流程）：碼是家屬用訊息傳給長輩、長輩再貼進 App 的，這條路上帶到空白或換行是常態。不剝的話長輩看到「查無此邀請碼」而他手上那張碼明明是對的——他會反覆重打然後放棄，而後台查不到任何原因（A-11，2026-07-29）。

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
| —（新增） | `WS /api/v1/ws/talk` | **對講機長連線**（spec 2026-07-28）：整輪對話走同一條 WebSocket，後端可主動送第二則訊息。認證走 query `token`（WebSocket 握手在 RN 與瀏覽器都不能自訂標頭），並以閘門複核同意，失敗以 close code 1008 關閉。上行：一個 binary 訊息＝一輪完整音檔；一個 JSON 訊息＝更新下一輪要用的位置（`{location, latitude, longitude}`，三者齊備才寫入）。⚠️ **位置訊框的欄位型別由伺服器把關**（V-03，2026-07-29）：`location` 必須是字串、座標必須是數字（`bool` 不算——`float(true)` 是 1.0，會把長輩記在幾內亞灣外海），任一不合就整筆丟掉並記 warning。**座標範圍同時把關**（V-04）：緯度 ±90、經度 ±180，超出即視同這輪沒有位置——原樣落庫不只是一筆髒資料，`LocationFacts` 會把它注入每一輪提示詞、附近地點搜尋會拿它當圓心，長輩問「附近有沒有藥局」會得到北極圈的答案。此處**不可只靠 App 自律**：型別錯會讓 `place.strip()` 拋 `AttributeError` 一路冒到讀迴圈，那裡只接 `WebSocketDisconnect`，於是整條連線被砍且不送 error 訊框——而且發作在長輩**下一次開口**時（位置訊框只是存進 pending），症狀是「講完一整句話連線就斷、那句話也沒進庫」。REST 的 `POST /turns` 因 FastAPI 強制轉型不受影響。下行皆帶 `turn_id`：`ack`（`text`／`audio_url`／`duration_ms`，模型決定要查東西時立刻送、音檔取自預錄語庫不現場合成）、`queued`（**容量閘門滿載時排隊告知位置**，spec 2026-07-30 §10 B2、P3 Task 2 接線，2026-07-31：`{position}`＝**排隊名次**（1-based，`position=1`＝目前排隊第一位）；⚠️ **不是「前面還有幾位」**——`limit=1` 時兩者剛好相等，但正式環境 `limit=TURN_CONCURRENCY_LIMIT`（2026-08-01 核定為 2，每 worker）時，排隊名次 1 的人前面其實還有 2 輪正在跑（只是不在佇列裡；全域則是 ×`WEB_WORKERS`），P4 前端顯示應走「您排第 N 位」而非「前面還有 N 位」；容量閘門與 `_MAX_CONCURRENT_TURNS` 的單連線併發上限是兩件不同的事，兩者並存）、`reply`（同 `POST /turns` 的欄位；**僅在沒有音檔時才是 JSON**，見下）、`error`（回退話術，含併發輪達上限、排隊逾時、每分鐘輪數保險絲觸發時的婉拒，三種情形共用同一句人話）。**回覆音檔改隨 binary 訊框直送**（2026-07-30 延遲優化 C1）：有音檔的那一輪不送 JSON `reply`，改送一個 binary 訊框＝`[4 bytes 大端序 header 長度][UTF-8 JSON header][m4a bytes]`，header 欄位與 `reply` 完全相同（`type` 亦為 `"reply"`）、`audio_url` 固定為空字串。原本的路是「後端上傳 Supabase→取簽章 URL→App 拿到 URL→App 再向 Supabase 下載」，音檔在網路上走兩趟；改成 bytes 直送後上傳降級為存證並排在推送之後。⚠️ **header 必須嵌在同一個訊框裡，不可靠「先送 JSON 再送 binary」的順序配對**：同一條連線最多三輪併發，兩輪幾乎同時算完時 `JSON(A)／JSON(B)／binary(A)／binary(B)` 的交錯完全可能，App 就會把 A 的音檔配上 B 的字幕。自我描述的訊框對交錯免疫，也不需要任何關聯狀態。⚠️ App 端仍必須同時吃得下兩種形式——TTS 失敗退純文字時沒有音檔可內嵌，那一輪照舊走 JSON。同時在跑的輪數上限 3。⚠️ `POST /turns` 保留為降級路徑，兩者共存 |
| `POST /api/app/turns` | `POST /api/v1/turns` | 對講機回合（raw body 音檔；上限 env 化 D-26）。**容量閘門**（spec 2026-07-30 §10 B2、P3 Task 2 接線，2026-07-31）：與 `WS /ws/talk` 共用同一個 `TurnAdmission`，滿載時排隊等待，逾時回 **503** `too_many_requests`（⚠️ 與認證節流的 429 是同一個錯誤碼、不同狀態碼——429 對應「client 打太快」，503 對應「伺服器容量暫時不足」，兩種語意刻意共用碼但以狀態碼區分，見 07 §4）；`error.message` 為既有的婉拒人話（與 WS 路徑同一句），非裸狀態碼。另有每位長輩每分鐘 30 輪的節流保險絲（純防前端重連迴圈狂送，對真人操作等同無限），觸發時回 **429** 同一碼同一句人話。回應自 2026-07-26 起多兩個欄位：`chunk_count`（整段回覆被切成幾段；>1 代表 `audio_url` 只是**第一段**，其餘用 `GET /turns/chunks/{index}` 依序取）與 `reply_digest`（取後續段落時帶上）。分段只對 App 通道啟用——LINE 一輪只能回一則語音，給它第一句等於把後面的話吞掉。選填 query：`location`＋`latitude`＋`longitude`（長輩地名＋模糊座標，App 端已四捨五入至 0.01 度；**三者齊備才寫入** `elder_locations`，寫入排在 dispatch 之前，缺任一即忽略、不清空既有值——spec 2026-07-17 長輩目前地點；座標範圍不合法（緯度 ±90／經度 ±180 之外）同樣**忽略而非 422**，V-04 2026-07-29——422 會連長輩那句話一起退掉，位置是加分項，為了 App 送錯一個參數讓長輩重講一次代價太大；**地名超過 100 字**同樣忽略，V-05 2026-07-29——實測 2 萬字的地名會原樣落庫且**每一輪都注入提示詞**，既燒 token 也是提示注入的入口。⚠️ 這個上限刻意訂得寬：地名被拒是**靜默**失敗，長輩那端的表現是金孫又開始反問「您人在哪裡」而後台查不出原因——App 送的是 `address.city ?? subregion ?? region`，全是短的行政區名） |
| —（新增） | `GET /api/v1/elder-notifications` | **長輩讀自己的 App 內通知**（X-01，2026-07-29 全面自動化測試）：長輩 Bearer token 認證，回本人 App 綁定 `external_id` 名下的訊息（用藥／回診提醒、主動關懷），形狀與家屬面 `GET /notifications` 相同（`[{content, created_at}]`、最近先、上限 50）。**為什麼補**：提醒送出＝`AppOutboundChannel` 落一筆 `app_notifications`，但先前只有家屬讀得到且只查家屬自己的 `external_id`——寫給長輩的那一列誰都讀不到，用藥／回診／主動關懷對純 App 家庭等於不存在（違反 PRD US-B2、BDD R4）。無 App 綁定回空陣列（非錯誤）；家屬 token 打此端點回 401。⚠️ 真推播（D-08 階段 5）到位後本端點不被取代，仍是推不到（App 未開、token 失效、換機）時的補拉路徑 |
| —（新增） | `POST /api/v1/push-tokens`／`DELETE /api/v1/push-tokens/{token}` | **裝置推播 token 註冊**（真推播 D-08 階段 5，2026-07-29）：長輩與家屬共用同一支端點——兩邊都要收推播（長輩收用藥提醒、家屬收危急警報），差別只在 token 綁到哪個主體，而**主體一律由 Authorization 決定、不由呼叫端宣告**（讓客戶端自報身分＝開一個「把別人的提醒導到我手機」的破口）。Request `{token, platform}`，platform ∈ `android`／`ios`（大小寫不敏感），其餘 400 `validation_error`；同一個 token 再打一次＝改綁（換人用同一台裝置）。回 201 `{registered}`——`PUSH_ENABLED=false` 的部署收下但不存並回 `registered:false`，讓 App 不必分辨伺服器版本。DELETE 只刪自己名下的（否則知道別人 token 的人可以讓對方從此收不到提醒），一律 204。⚠️ 推播為加分項：訊息一律先落 `app_notifications` 再推，推播失敗不影響落庫，App 開啟時仍讀得到 |
| `current_app_guardian` 屬性 | **刪除** | 死碼（D-28） |

### 觀測後台（tags: admin）

| as-is | to-be | 說明 |
| :--- | :--- | :--- |
| `GET /api/admin/overview`／`elders`／`messages`／`elders/{elder_id}/timeline`／`traces/{trace_id}` | 同路徑掛 `/api/v1/admin/` | messages 加 `before` 回翻（D-29）；`traces/{trace_id}` 回應加 `opik_url`（工程觀測開啟且捕捉到 Opik trace id 時＝直達 Opik 的深連結，否則空字串，前端據此隱藏連結）|
| —（新增） | `GET /api/v1/admin/elders/{elder_id}/reminders`／`memory`／`account`／`risk-notifications`、`GET /api/v1/admin/jobs` | 內測基礎建設（spec 2026-07-12）：長輩詳情四分頁＋排程狀態，唯讀、`X-Admin-Key` 守門 |
| —（加欄位＋母體變更） | `GET /api/v1/admin/jobs` | 跨程序監控（2026-07-27）：母體由「本程序綁得出執行體的 job」改為 `cron/registry.py` 的全系統宣告，每列加 `owner`（負責執行的程序，字面＝`kinsun.sh` 服務名）與 `can_run_now`（後台能否就地觸發）。**加法**：既有欄位與狀態碼不變，但清單會多出 `rag-weekly-refresh`（`RAG_REFRESH_ENABLED=true` 時）。⚠ 前端若對每列都畫「立即執行」按鈕，需改看 `can_run_now`，否則按下去會拿到 409 |
| —（加欄位） | `GET /api/v1/admin/jobs` | 逾期偵測（2026-07-26 全流程模擬實測）：每列加 `due_at`／`late_seconds`／`is_overdue`，`meta` 加 `overdue`（逾期的 job 名陣列）與 `warnings`（人話告警）。判定＝`croniter(cron, last_run).get_next()` 早於現在超過 5 分鐘；`last_run_at` 為 null（從未跑過）者不判逾期。**加法**，舊前端忽略即維持原行為 |
| `/elders/{id}/medications`、`/elders/{id}/appointments`（**移除**） | `GET/POST/PUT/DELETE /api/v1/elders/{elder_id}/schedules[/{group_id}]` | 統一排程（D-76 P3）：用藥、回診與長輩自訂三類合成單一資源。**操作單位為 group（一件事）而非單一鬧鐘**——家屬按刪除時想刪的是「這個藥」，不是「這個藥的早上那次」。`kind` query 可篩類型；PUT 走 replace_group（先驗證再動手，失敗時原組原封不動）；DELETE 為軟刪（寫 `cancelled_at`，永久保留）。 |
| `POST .../reminders/dispatch`（body 改） | 同路徑，body 由 `{kind, slot}` 改為 `{kind}`（medication／appointment／custom） | 改接統一派送（D-76 P5）。⚠ 手動觸發**不寫** `fired_at`／`settled_at`——測試動作不可吃掉長輩當天真正該收到的那一則。 |
| `GET .../admin/elders/{id}/reminders`（回應改） | 同路徑，`medications`＋`appointments` 兩份清單合成 `schedules` 一份 | kind 欄位保留分類，另有 `created_by` 區分家屬設的與長輩自己交代的。 |
| —（新增） | `POST /api/v1/admin/jobs/{job_name}/run`、`POST /api/v1/admin/elders/{elder_id}/reminders/dispatch` | 內測手動觸發（spec 2026-07-12）：需 `X-Admin-Key`＋`INTERNAL_TESTING_ENABLED=true`（否則 403 `internal_testing_disabled`）；RPC 動作式路徑為 admin 內部工具刻意例外；不寫 `scheduler_state` |
| —（新增） | `GET /api/v1/meta` | 公開端點（無認證）：回 `{internal_testing: bool}` 供 App／admin 前端決定內測功能顯示（spec 2026-07-12） |
| —（新增） | `GET /api/v1/demo-status` | 公開端點（無認證，spec 2026-07-30 W-03）：網頁版前端（`web/`）進站即查，據此決定「開始使用」能不能按。回應 `data` 形狀 `{overall, components}`——`overall` ∈ `available`／`degraded`／`starting`／`down`（優先序：停機 > 啟動中 > 部分受限 > 可用）；`components` 為 `database`／`asr`／`tts`／`llm`／`scheduler` 五項，各 ∈ `ok`／`loading`／`down`／`unknown`。刻意粗粒度——不回版本、主機名、埠號或例外訊息，那些對前端沒用、對掃描的人很有用。`database`／`asr` 為關鍵項，任一 `down` 即整體 `down`（對講機是本產品唯一核心互動）。**結果快取 5 秒＋single-flight**（`create_demo_status_router` 的 `cache_seconds`）：公開端點不可成為壓力測試 ASR／TTS `/healthz` 的放大器。⚠️ 快取在探測**完成後**才更新，期間到達的請求會一起穿透——一次 cache miss 要兩次 healthz（各 1.5s 逾時）＋埠探測＋DB＋traces 統計＋每支排程 job 兩次查詢，ASR／TTS 真的掛掉時最慢約 4 秒，而這支端點免認證、經 ngrok 對外、底下 handler 全是同步 `def` 共用 anyio 那 40 條執行緒池。故加一把 `threading.Lock`：拿不到鎖就**回上一份快取（即使過期）**，只有冷啟動（連一份都還沒有）才等。⚠️ 探針分項不齊時在 `create_demo_status_router` **建立當下就擲 `ValueError`**：`overall_of` 用 `components.get(name)` 判關鍵項，鍵不存在時是 `None`、`None != "down"`，漏接一支探針會讓「ASR 掛掉＝整體停機」悄悄失效（畫面顯示 available、按鈕可按）。實作見 `web/routers/demo_status.py` |
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
| v1.23 | 2026-07-31 | **網頁版前端 P3 對講機容量閘門接線**（Task 2）：`WS /ws/talk` 下行新增 `queued` 訊框（`{turn_id, position}`）；`POST /turns` 超限（含排隊逾時）改回 **503** `too_many_requests`——與認證節流的 429 同碼不同狀態碼（429＝client 打太快、503＝伺服器容量暫時不足），`error.message` 沿用既有婉拒人話與 WS 同一句；兩條路徑另加每位長輩每分鐘 30 輪的節流保險絲，觸發時 WS 送 `error` 訊框、POST 回 429，同碼同一句人話。錯誤碼表補一列 `too_many_requests`／503 的新用法 |
| v1.22 | 2026-07-31 | `GET /api/v1/demo-status` 兩修（P1 全分支審查 I5／I6）：①**探針分項不齊在建立路由當下就擲 `ValueError`**——`overall_of` 用 `components.get(name)` 判關鍵項，鍵不存在是 `None`、`None != "down"`，漏接一支探針會讓「ASR 掛掉＝整體停機」悄悄失效，`COMPONENT_NAMES` 原本全庫零引用；②**快取加 single-flight**——快取在探測完成後才更新，期間到達的請求會一起穿透去打同一台正在重啟的 GPU 服務（單次 miss 最慢約 4 秒），拿不到鎖改回上一份快取（即使過期），冷啟動才等 |
| v1.21 | 2026-07-31 | 新增 `GET /api/v1/demo-status`（網頁版前端 P1 地基，任務 12，spec 2026-07-30 W-03）：公開免認證的運營狀態端點，供 `web/` 進站決定「開始使用」可否點擊；五分項＋整體狀態四值、結果快取 5 秒防公開端點被當健康檢查放大器 |
| v1.20 | 2026-07-30 | **`WS /ws/talk` 回覆音檔改隨 binary 訊框直送**（延遲優化 C1）：十輪實測回覆上傳中位 0.54 秒、尖峰 2.37 秒，而長輩要等完那一趟才**開始**下載第二趟。改成一個自我描述訊框（`[4B 大端 header 長度][JSON header][m4a bytes]`）把音檔直接推下去，Supabase 上傳降級為存證並排在推送之後（`replies.audio_url` 仍是後台回放的依據）。⚠️ header 嵌在同一訊框而非「先 JSON 後 binary」：同一條連線最多三輪併發，訊框交錯會讓順序配對把 A 的音檔配上 B 的字幕——這種錯誤看起來完全正常。⚠️ 存證上傳失敗**不退回文字**（長輩已經聽到了，只是後台少一筆回放），與非內嵌那條路的「上傳失敗退文字」刻意不同——那裡失敗等於長輩什麼都拿不到。App 端兩種形式都要吃得下 |
| v1.0 | 2026-07-08 | 初版：D-23～D-29 契約定稿 |
| v1.1 | 2026-07-17 | turns 補位置三參數（location／latitude／longitude 模糊座標，三者齊備才寫入）；追認 7/12–7/14 已回填而未升版的內容（sessions/all、内測端點、守則端點、錯誤碼中央註冊等） |
| v1.2 | 2026-07-17 | 稱謂欄位（elders.nickname）：POST /elders 收選填 nickname、GET /elders 回傳 nickname、新增 PUT /elders/{elder_id}/profile 補設稱謂 |
| v1.4 | 2026-07-25 | 新增 `GET /api/v1/admin/news`（話題新聞檢視，D-74 消費端）。 |
