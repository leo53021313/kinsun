# 頁面清單與內容模型

> 版本：v1.3｜日期：2026-07-30｜狀態：第一階段評審稿；已同步 D-76、X-01、WS 五態與純文字降級
> 數量以實際路由為準：Expo App 12 頁、LIFF 3 頁、Admin 7 頁。Admin 長輩詳情五分頁不重複計頁。

## 1. Expo App（12 頁）

| 頁面 | 角色 | 頁面目標 | 主要 CTA | 次要操作 | 核心資訊 | API | 認證 | 狀態 | 無障礙注意事項 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/` | 全角色 | 讀取 Session 並自動分流 | 無 | 無 | 載入狀態 | 無 | SecureStore 本機 Session | loading、導向 | spinner 需有可讀名稱；避免畫面閃爍 |
| `/role` | 全角色 | 選擇長輩或家屬路徑 | 我是長輩／我是家屬 | 內測角色切換不在此 | 兩種角色用途 | 無 | 無 | 預設 | 每個卡片 48pt；文字不可只靠圖示 |
| `/elder/bind` | 長輩 | 完成首次裝置配對 | 掃描／完成綁定 | 手動輸入、返回 | 相機、代碼、錯誤 | `bindElderDevice` | 無 → Elder Bearer | 權限、掃描、輸入、錯誤、成功 | 權限目的、KeyboardAvoiding、錯誤公告 |
| `/elder/login` | 長輩 | 已配對後以帳密重登 | 登入 | 前往綁定、返回 | 手機號碼、密碼 | `loginElder` | 無 → Elder Bearer | busy、401、403 | 可見 label；403 提供綁定回復 |
| `/elder/talk` | 長輩 | 完成語音陪伴對話 | 104dp 麥克風（按住放開／短按兩次） | 提醒鈴鐺、登出、內測切換 | A-Kin、回覆、權限、五態 | `WS /ws/talk`、`postTurn` 降級、`getMeta` | Elder Bearer | Idle、Listening、Thinking、Speaking、Error、權限、403 | ack 播完維持 thinking；有音檔 reply 播完才 idle、純文字 reply 抵達即 idle；error 不偽裝 idle；動態公告、長回覆捲動 |
| `/elder/notifications` | 長輩 | 閱讀金孫留下的提醒 | 回去講話 | 無 | 時間、內容、本機已讀水位 | `listElderNotifications` | Elder Bearer | loading、empty、list、error | 長輩字級與 56dp 返回；不用「通知」術語；載入成功才更新水位 |
| `/guardian/login` | 家屬 | 登入家屬帳號 | 登入 | 前往註冊、返回 | email、密碼 | `loginGuardian` | 無 → Guardian Bearer | busy、401、error | label 關聯、密碼語意、錯誤焦點 |
| `/guardian/register` | 家屬 | 建立家屬帳號 | 建立帳號 | 返回登入 | 姓名、email、密碼 | `registerGuardian` | 無 → Guardian Bearer | busy、validation、error | 鍵盤、錯誤摘要、同意文案可讀 |
| `/guardian/home` | 家屬 | 查看長輩並新增長輩 | 新增長輩／選長輩 | 通知、複製碼、登出 | 長輩卡、未讀、同意、QR／代碼 | `listElders`、`createElder`、`listNotifications` | Guardian Bearer | loading、empty、1／多位、未讀、建立結果、error | 初載與空狀態分開；卡片名稱清楚 |
| `/guardian/elder/:id` | 家屬 | 掌握一位長輩的照護狀況 | 管理行程 | 邀請家屬、設帳密、返回 | 報告、摘要、統一行程、邀請 | `getHealthReport`、`listDailySummaries`、`listSchedules`、`createGuardianInvite`、`setElderAccount` | Guardian Bearer＋資源可及 | loading、normal、各區 empty、new event、partial／total error | 不顯示逐字稿；區塊 heading；局部失敗 |
| `/guardian/elder/:id/schedules` | 家屬 | 管理用藥／回診／其他提醒 | 新增／儲存 | 類型切換、編輯、刪除、取消 | 類型、內容、時間規則、清單 | schedule group CRUD | Guardian Bearer＋資源可及 | loading、empty、data、create、edit、validation、confirm、error | radio／checkbox 語意、時間格式提示、刪除後果 |
| `/guardian/notifications` | 家屬 | 查看 App 通知 | 返回首頁 | 無 | 時間、內容、本機已讀水位 | `listNotifications` | Guardian Bearer | loading、empty、list、error；類型／單筆已讀待決策 | 嚴重度不只色彩；載入成功才更新水位 |

## 2. LIFF（3 頁）

| 頁面 | 角色 | 頁面目標 | 主要 CTA | 次要操作 | 核心資訊 | API | 認證 | 狀態 | 無障礙注意事項 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/liff/` | 家屬 | 查看／新增長輩 | 新增長輩 | 進行程、報告 | 長輩清單、邀請碼 | `listElders`、`createElder`、`generateGuardianInvite` | LIFF idToken | initializing、loading、empty、error、data | 真正 label、busy、空狀態與成功公告 |
| `/liff/elders/:id/schedules` | 家屬 | 管理用藥／回診／其他提醒 | 儲存行程 | 返回、類型切換、編輯、刪除 | 清單、類型、內容、時間規則 | LIFF schedule group CRUD | LIFF idToken＋資源可及 | loading、empty、data、form、error | radio／checkbox、刪除確認、鍵盤、錯誤關聯 |
| `/liff/elders/:id/health-report` | 家屬 | 閱讀健康報告 | 返回長輩清單 | 無 | 危急事件、提醒 | `getHealthReport` | LIFF idToken＋資源可及 | loading、empty、error、data | 嚴重度文字；不把無資料寫成健康正常 |

LIFF 沒有每日摘要入口，符合 D-09 的施工界線。`已決議＋已實作`

## 3. Admin（7 頁）

| 頁面 | 角色 | 頁面目標 | 主要 CTA | 次要操作 | 核心資訊 | API | 認證 | 狀態 | 無障礙注意事項 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/admin/` | 維運人員 | 掌握系統健康與告警 | 進入異常脈絡 | 主導航 | KPI、趨勢、階段統計、alerts | `getOverview` | X-Admin-Key | loading、data、disconnected、alert | 圖表需表格替代；警示不只紅色 |
| `/admin/messages` | 維運人員 | 查看即時與歷史訊息流 | 開 trace／載入更早 | 主導航 | 方向、內容、時間、trace id | `listMessages`、`listMessagesBefore` | X-Admin-Key | 初載、data、disconnected、loading older、empty | 資料列語意、焦點保留、live polling 不搶焦點 |
| `/admin/elders` | 維運人員 | 找到長輩 | 開詳情 | 主導航 | 名稱、最近活動、輪次 | Admin `listElders` | X-Admin-Key | loading、data、empty、error | 尚未載入與空清單分開；可鍵盤開啟 |
| `/admin/elders/:elderId` | 維運人員 | 查看長輩觀測資料 | 切換五分頁／開 trace | 日期選擇 | 時間軸、提醒、記憶、帳號、危急 | timeline、reminders、memory、account、risk notifications | X-Admin-Key | 每個分頁 loading／empty／error／data | `tablist`／`tab`／`tabpanel`、aria-selected、方向鍵 |
| `/admin/traces/:traceId` | 維運人員 | 找出處理鏈失敗 | 回來源脈絡 | 無 | Webhook、ASR、RAG、風險、LLM、TTS、reply | `getTrace` | X-Admin-Key | loading、404／error、partial、data | 依處理順序；狀態文字；長內容可收合 |
| `/admin/news` | 維運人員 | 檢視已擷取的話題新聞 | 開啟原文 | 天數範圍、主導航 | 標題、來源、發布時間、網址 | `listNews` | X-Admin-Key | loading、empty、error、data | 原文連結名稱清楚；日期與來源不可只靠位置 |
| `/admin/system` | 維運人員 | 查看排程與 RAG 狀態 | 內測執行工作 | 主導航 | jobs、cron、last run、RAG active release | `listJobs`、`getRagStatus`、`runJob`、`dispatchReminder` | X-Admin-Key；手動動作另受 internal testing | loading、data、warning、error、running | 執行前說明影響；busy／完成公告；錯誤可重試 |

### Admin 認證殼層（不另算頁）

`KeyForm` 在沒有金鑰或 401 時取代路由內容。它不是第八個 route，但必須納入線框與無障礙檢查：可見 label、錯誤說明、清除／重新輸入與密碼型輸入語意。`已實作＋提案`

## 4. 頁面內容模型

### 長輩端

```text
ElderSession
├─ elder_id
├─ name
└─ token

VoiceInteraction
├─ permission_state
├─ avatar_state: idle | listening | thinking | speaking | error
├─ reply_text
├─ reply_audio
├─ optional_location
└─ recovery_reason
```

`recovery_reason` 是線框需要的呈現概念，現有 shared type 沒有獨立欄位。`提案`

### 家屬端

```text
GuardianSession
└─ Elder[]
   ├─ HealthReport
   │  ├─ RiskEventItem[]
   │  └─ ReminderItem[]
   ├─ DailySummary[]
   ├─ ScheduleGroup[]
   ├─ GuardianInvite
   └─ ElderAccount
```

### 通知

```text
As-is AppNotification
├─ content
└─ created_at

若要實作線框概念，待決策欄位可能包括
├─ notification_id
├─ kind
├─ severity
├─ elder_id / elder_name
└─ read_at 或 read state
```

後半段不是 API 規格，只是把視覺需求反推成待討論欄位；不得直接實作。`待決策`

### Admin Trace

```text
TraceDetail
├─ webhook_event
├─ asr_call
├─ rag_calls[]
├─ risk_events[]
├─ llm_calls[]
├─ tts_call
└─ reply
```

## 5. 路由一致性檢查

- Expo Router 實際頁面檔：12。`通過`
- LIFF React Router `<Route>`：3。`通過`
- Admin React Router `<Route>`：7。`通過`
- 頁面名稱與 `docs/dev/17_前端資訊架構.md:73` 一致。`通過`
- 長輩詳情五分頁未誤算為路由。`通過`
- 家屬頁面清單沒有加入完整逐字對話。`通過`
