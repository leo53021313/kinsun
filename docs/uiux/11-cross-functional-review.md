# Kinsun UI／UX 跨職能評審 Pre-read

> 版本：v1.0｜日期：2026-07-25｜狀態：待團隊拍板
> 範圍：P0 通知資料契約、長輩端 403 綁定失效回復
> 注意：本文件中的「建議」不是正式決議；拍板後才同步 `docs/dev/`、API 契約與工程工作項目。

## 1. 本次要拍板什麼

第一、第二階段已完成三端 UX Audit、資訊架構、流程與低保真線框。進入可點擊 Prototype 或高保真 UI 前，有兩個跨產品、Safety、後端與 App 的 P0 問題必須先決定：

1. 家屬通知目前只有 `content` 與 `created_at`，App 無法可靠區分風險警示、回診提醒或其他通知。
2. 長輩對話收到 403 後雖先寫入說明文字，接著立即清除 Session；路由守門可能使說明消失，使用者看不到可操作的回復路徑。

本次不拍板品牌視覺、最終色彩、字型、虛擬角色、後端逐筆已讀機制，也不變更 Risk Engine 的責任邊界。

## 2. 60 分鐘評審議程

| 時間 | 主題 | 會議輸出 |
| --- | --- | --- |
| 0–5 分 | 確認既有決策與不可變邊界 | 無異議的 Guardrails |
| 5–30 分 | UX-D01 通知資料契約 | 選定方案、欄位與責任人 |
| 30–50 分 | UX-D02 403 回復 | 選定狀態模型、文案與導向 |
| 50–60 分 | 驗收與後續拆工 | Owner、期限、未決問題 |

會前建議先看：

- [家屬危急通知線框](wireframes/export/app-guardian-notifications-critical.svg)
- [家屬提醒通知線框](wireframes/export/app-guardian-notifications-reminder.svg)
- [通知已查看狀態線框](wireframes/export/app-guardian-notifications-read-state.svg)
- [長輩 403 回復線框](wireframes/export/app-elder-talk-error-403.svg)
- [通知水位流程](diagrams/export/flow-notification-watermark.svg)
- [403 重新綁定流程](diagrams/export/flow-elder-403-rebind.svg)

## 3. 不可協商的產品與 Safety 邊界

| 邊界 | 本次設計含義 |
| --- | --- |
| Risk Engine 是風險等級與是否通知的唯一權威 | App、RAG 或 LLM 都不能解析文案後自行判斷嚴重度。 |
| L2 通知全部家屬；L1 僅進每日摘要 | 通知契約不能把 L1 包裝成即時危急警示。 |
| L2 每次都通知，現階段不做冷卻、去重或升級策略 | UI 可合併視覺群組，但不可擅自省略事件。 |
| 家屬不得看到完整逐字對話 | `content` 必須是家屬可見的安全摘要，不得回傳 transcript。 |
| App 目前是拉取通知＋本機時間水位 | 在後端已讀回條完成前，只能稱「上次查看後的新通知」，不能聲稱逐筆已讀已跨裝置同步。 |
| 首次綁定仍走 QR／邀請；帳密只用於再次登入 | 403 回復必須同時提供「重新綁定」與「帳密登入」，不可把兩者混為同一流程。 |

## 4. 現況證據

| 證據 | 現況與影響 |
| --- | --- |
| `shared/types.ts` | `AppNotification` 只有 `content`、`created_at`。 |
| `src/kinsun/notifications/store.py` | 儲存模型已有穩定 `app_notification_id`，但 API 未提供。 |
| `src/kinsun/web/routers/notifications.py` | `/notifications` 回應只輸出內容與時間。 |
| `src/kinsun/channels/app/outbound.py` | App outbound 只接收 `external_id`、`text`，結構化 metadata 尚未穿過 Channel seam。 |
| `app/src/app/guardian/notifications.tsx` | 清單只能顯示時間與內容，React key 由時間＋內容臨時組合。成功載入後立即儲存最新時間水位。 |
| `app/src/app/guardian/home.tsx` | 未讀 badge 以 `created_at > seen_at` 計算；取得失敗時不顯示未讀數。 |
| `src/kinsun/pipeline.py`、`src/kinsun/safety/notifier.py` | Risk Engine 先判定 L2，再於生成回覆前通知全部家屬；RAG／LLM 不授權通知。 |
| `app/src/app/elder/talk.tsx` | 403 時先設定綁定失效文案，再呼叫 `signOut()`。 |
| `app/src/lib/SessionProvider.tsx` | `signOut()` 清除目前 Session，未保留離場原因。 |
| `app/src/app/elder/talk.tsx` 路由守門 | Session 清除後會導回 `/role`，原頁文案可能來不及被理解。 |

## 5. UX-D01：通知資料契約

### 5.1 問題陳述

目前 App 若要呈現不同通知樣式，只能從自由文字猜測類型或嚴重度。這會把 Safety 決策偷偷移到前端，也會因文案調整、語系或 LLM 輸出而失效。

### 5.2 方案比較

| 方案 | 作法 | 優點 | 風險／成本 | 建議 |
| --- | --- | --- | --- | --- |
| A. 前端解析 `content` | 以關鍵字或正規表示式推斷風險與類型 | 工程量最小 | 破壞 Risk Engine 權威；易誤判；文案與邏輯耦合 | 不採用 |
| B. 加法式 typed contract，暫留本機水位 | Domain producer 提供 `kind`／`risk_tier`，一路寫入儲存層與 API；既有 `content` 保留 | 可安全支援通知樣式與穩定 key；相容既有 UI；範圍可控 | 需修改 Channel seam、Schema、API、shared type 與 App | **建議採用** |
| C. typed contract＋伺服器逐筆已讀 | 在 B 之外新增每位家屬的 read receipt 與同步 API | 語意最完整、跨裝置一致 | Schema、併發、離線同步與遷移範圍較大 | 後續獨立決策 |

### 5.3 建議契約

以下為評審用概念契約，不是已核准的 API：

```json
{
  "app_notification_id": "uuid",
  "elder_id": "uuid",
  "elder_name": "林阿嬤",
  "kind": "risk_alert",
  "risk_tier": 2,
  "content": "偵測到需留意的安全事件，請儘快關心長輩。",
  "created_at": 1784908800.0
}
```

欄位建議：

| 欄位 | 規則 |
| --- | --- |
| `app_notification_id` | 後端穩定識別碼；供列表 key、追蹤與未來 read receipt 使用。 |
| `elder_id` | 通知所屬長輩業務主鍵；不得用 LINE 外部識別碼代替。 |
| `elder_name` | 顯示用快照；是否由 API join 或儲存時快照，由後端拍板。 |
| `kind` | 初版候選：`risk_alert`、`appointment_reminder`、`medication_reminder`、`proactive_message`。由事件產生端寫入，前端不可從 `content` 推斷。 |
| `risk_tier` | `risk_alert` 由 Risk Engine 寫入，目前只允許 `2`；非風險通知為 `null`。 |
| `content` | 家屬可見安全摘要；不得包含完整逐字對話。 |
| `created_at` | epoch 秒，沿用專案時間契約。 |

相容與降級規則：

1. 新欄位採加法式遷移；部署期間舊資料仍可顯示。
2. App 遇到未知或缺少 `kind` 時顯示中性「通知」，不得解析 `content` 猜測。
3. `/notifications` 失敗時不得更新本機水位。
4. 現階段保留本機 `seen_at`；UI 文案使用「新通知」而非「未讀」，避免暗示跨裝置已讀同步。
5. 顏色與 icon 只能輔助辨識；風險層級需有明確文字標籤。

### 5.4 建議 UI 對應

| `kind` | 建議標籤 | UI 層級 |
| --- | --- | --- |
| `risk_alert`＋`risk_tier: 2` | 需留意 | 高優先；置頂視覺、文字標籤、可直接前往長輩狀況。 |
| `appointment_reminder` | 回診提醒 | 一般提醒；顯示日期／時間與長輩。 |
| `medication_reminder` | 用藥提醒 | 一般提醒；若此類尚未送給家屬，先支援契約但不製造假資料。 |
| `proactive_message` | 關懷通知 | 一般資訊。 |
| 未知／缺值 | 通知 | 中性 fallback；不顯示推測的嚴重度。 |

### 5.5 驗收條件

- [ ] 同一通知在重新整理後維持同一 `app_notification_id`。
- [ ] `kind` 由 domain producer 傳入並完整穿過 Channel、Store、API 與 App。
- [ ] `risk_tier` 只採信 Risk Engine 結果，前端沒有文案解析邏輯。
- [ ] 家屬 API 與記錄中沒有完整逐字對話。
- [ ] 未知 `kind` 有中性、安全的 fallback。
- [ ] API 失敗不前移 `seen_at`；成功載入才更新水位。
- [ ] 清單不用 `created_at + content` 當永久識別。
- [ ] Loading、empty、error、舊資料與混合版本資料皆有測試。
- [ ] VoiceOver／TalkBack 可朗讀通知類型、長輩、時間與內容，且不只靠顏色區分。

### 5.6 拍板欄

| 項目 | 需填內容 |
| --- | --- |
| 選定方案 | `A`／`B`／`C` |
| `kind` enum |  |
| `elder_name` 策略 | API join／寫入時快照／不提供 |
| 本機水位文案 |  |
| Product Owner／日期 |  |
| Safety Owner／日期 |  |
| Backend Owner／日期 |  |
| App Owner／日期 |  |

## 6. UX-D02：403 綁定失效回復

### 6.1 問題陳述

403 是 Session 已不再對應有效長輩綁定的產品狀態，不應只被當成瞬間錯誤。現況先設定錯誤文案、再立即清 Session，路由守門接著離開對話頁；使用者可能只感覺「突然跳回去」，不知道下一步。

### 6.2 方案比較

| 方案 | 作法 | 優點 | 風險／成本 | 建議 |
| --- | --- | --- | --- | --- |
| A. 維持立即 `signOut()` | 依目前流程回 `/role` | 無新增狀態 | 原因與行動消失；不符合可回復錯誤原則 | 不採用 |
| B. 以 query parameter 傳回 `/role` | `/role?reason=binding_lost` | 修改小、可直接導向 | URL 狀態易殘留；需防止重播與手動拼接 | 備選 |
| C. 新增 `/elder/recovery` | 專用回復頁 | 任務最聚焦 | 新增第 13 個 App 頁面與額外路由維護 | 暫不採用 |
| D. SessionProvider 保留非敏感離場原因 | 清除失效的 elder Session，同時以 `SessionExitReason` 暫存原因；既有 `/role` 顯示回復區塊 | 不新增頁面；語意清楚；可區分登出、過期與綁定失效 | 需設計生命週期與測試雙 Session | **建議採用** |

### 6.3 建議狀態模型

概念介面：

```ts
type SessionExitReason =
  | "elder_binding_lost"
  | "session_expired"
  | null;
```

建議流程：

1. 對話 API 回傳 403。
2. 呼叫概念動作 `invalidateCurrentSession("elder_binding_lost")`。
3. 僅清除失效的長輩 Session；保留另一角色的有效 Session。
4. 路由守門導向既有 `/role`。
5. `/role` 讀取 `SessionExitReason`，以可朗讀的警示區塊說明原因並提供兩條回復路徑。
6. 使用者選擇路徑或登入／綁定成功後清除 reason；手動登出不得顯示綁定失效。

若 App 被系統終止後重新開啟，回復原因可以消失，但使用者仍應安全停在角色選擇頁；原因狀態不得包含 token、LINE ID 或其他敏感資料。

### 6.4 建議文案與行動

```text
這台手機需要重新連結
目前的長輩綁定已失效。請家人協助重新綁定，或使用先前設定的帳號密碼登入。

主要按鈕：重新綁定
次要按鈕：用帳密登入
```

導向：

- 「重新綁定」→ `/elder/bind`
- 「用帳密登入」→ `/elder/login`

不可顯示 `403`、`not_paired`、token 或內部錯誤碼；若帳密從未設定，登入頁仍需以既有錯誤處理引導回綁定流程。

### 6.5 驗收條件

- [ ] 403 後使用者一定能看到「為什麼離開」與「下一步」，不只是一閃而過的文案。
- [ ] 沒有重新導向迴圈或受保護頁面閃爍。
- [ ] 「重新綁定」與「用帳密登入」皆可操作且返回路徑明確。
- [ ] 手動登出不會被誤標為綁定失效。
- [ ] 401 Session 過期與 403 綁定失效使用不同文案。
- [ ] 清除長輩 Session 不會刪除另一角色的有效 Session。
- [ ] App 重啟後即使 reason 不再存在，仍安全落在 `/role`。
- [ ] 警示區塊具有可被輔助科技辨識的 `alert` 語意，焦點順序先說明再到主要按鈕。
- [ ] 單元測試涵蓋 reason 生命週期；導覽測試涵蓋 403、手動登出、雙 Session 與成功回復。

### 6.6 拍板欄

| 項目 | 需填內容 |
| --- | --- |
| 選定方案 | `A`／`B`／`C`／`D` |
| 401／403 文案 |  |
| reason 是否跨 App 重啟保存 | 建議：否 |
| 雙 Session 清除策略 |  |
| Product Owner／日期 |  |
| App Owner／日期 |  |
| QA Owner／日期 |  |

## 7. 跨職能責任

| 職能 | 必須確認 |
| --- | --- |
| Product | 標籤、文案、優先順序、資料最小化與成功指標。 |
| Safety／Risk Engine | `risk_tier` 的產生與不可被下游覆寫；L1／L2 行為。 |
| Backend／Channel | typed metadata 的 seam、Schema 遷移、API 相容與穩定 ID。 |
| App | 降級顯示、水位語意、SessionExitReason、雙 Session 與無障礙。 |
| QA | 契約測試、混合版本、錯誤回復、隱私與輔助科技測試。 |
| Design | 依已拍板契約更新 Prototype、狀態矩陣與高保真規格。 |

## 8. Go／No-go Gate

| 工作 | 目前狀態 |
| --- | --- |
| 品牌探索、Moodboard、一般頁面 Prototype | 可並行，但不得凍結 P0 通知與 403 畫面。 |
| 通知高保真 UI 與元件 API | **No-go**，等待 UX-D01 拍板。 |
| 403 高保真 UI 與導覽規格 | **No-go**，等待 UX-D02 拍板。 |
| 正式 API、Schema 或產品程式碼實作 | **No-go**，需先完成決策與工程拆工。 |

## 9. 會議結論紀錄

| Decision ID | 結論 | Owner | 日期 | 待辦／期限 |
| --- | --- | --- | --- | --- |
| UX-D01 | 待拍板 |  |  |  |
| UX-D02 | 待拍板 |  |  |  |

會後：

1. 將核准決策寫入 `docs/dev/00_決策清單.md`，並依 `docs/dev/15_文檔與維護指南.md` 同步受影響文件與 `docs/dev/README.md`。
2. Backend、App、QA 依決策拆成可獨立驗收的工程工作項目。
3. Design 只依已拍板契約更新通知與 403 Prototype；未拍板欄位維持 `待決策`。
