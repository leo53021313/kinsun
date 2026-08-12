# Sitemap／資訊架構

> 版本：v1.2｜日期：2026-07-30｜狀態：第一階段評審稿；已同步 D-76、X-01、admin 新聞頁與 WS 純文字降級
> 原則：全景只表達三端邊界；詳細路由、API 與認證各自拆圖，避免超寬與交叉線。

## 1. 三端全景

![三端全景資訊架構](diagrams/export/ia-three-surface-overview.svg)

| 端 | 主要角色 | 首要目標 | 導覽深度 | 狀態 |
| --- | --- | --- | --- | --- |
| Expo App | 長輩、家屬 | 語音陪伴與日常照護 | 長輩 1 層主畫面；家屬最高 3 層 | `已實作` |
| LIFF | 家屬 | 凍結維運的照護管理與報告 | 清單 → 資源頁 | `已實作` |
| Admin | 維運人員 | 系統觀測與異常排查 | 主導航 → 長輩詳情 → trace | `已實作` |

## 2. Expo App

![Expo App 資訊架構](diagrams/export/ia-expo-app.svg)

```text
/
└─ 依 Active Session 自動導向
   ├─ Elder Session → /elder/talk
   ├─ Guardian Session → /guardian/home
   └─ 無 Session → /role

/role
├─ 長輩
│  ├─ /elder/bind
│  ├─ /elder/login
│  └─ /elder/talk
│     └─ /elder/notifications
└─ 家屬
   ├─ /guardian/login
   ├─ /guardian/register
   └─ /guardian/home
      ├─ /guardian/notifications
      └─ /guardian/elder/:elderId
         └─ /schedules
```

`RoleSwitcher` 是內測元件，不是第 13 頁。`已實作`

## 3. 長輩端

![長輩端資訊架構](diagrams/export/ia-elder-app.svg)

### 資訊層級

1. **回復入口**：首次綁定或已配對帳密重登。
2. **權限準備**：麥克風是完成核心任務的必要條件；定位是可拒絕的附加條件。
3. **核心對話**：Idle、Listening、Thinking、Speaking、Error；ack 語音播完維持 Thinking，正式 reply 結束才回 Idle；若 reply 沒有音檔，訊框抵達即以純文字收尾回 Idle。
4. **可理解回復**：麥克風拒絕、定位拒絕、網路失敗、403。

### 架構約束

- 對話頁不加入複雜主導航。`推論`
- 主要 CTA 永遠是 104dp 語音按鈕；56dp 提醒鈴鐺、登出與內測切換必須降階。`已決議＋已實作`
- 403 必須在清除 Session 後保留「為什麼」與「如何回復」。`推論`
- 長回覆可捲動，麥克風操作區與安全區域保持可達。`已決議`

## 4. 家屬端

![家屬端資訊架構](diagrams/export/ia-guardian-app.svg)

### 內容模型

```text
家屬
└─ 長輩（可多位）
   ├─ 近 30 天健康報告
   │  ├─ 危急事件
   │  └─ 提醒紀錄
   ├─ 每日摘要（不含完整逐字稿）
   ├─ 全部行程
   │  ├─ 用藥
   │  ├─ 回診
   │  └─ 其他提醒
   ├─ 家屬邀請
   └─ 長輩登入帳密代辦
```

### 導覽原則

- 首頁以「長輩」為第一層資訊主體，不以功能分類拆散同一長輩資料。`推論`
- 詳情頁採漸進揭露；報告與摘要先提供概況，再進統一行程管理。`推論`
- 通知是跨長輩的時間流；返回長輩詳情時要保留事件脈絡。`推論`
- 完整逐字對話不得出現在家屬 IA。`已決議`

## 5. LIFF

![LIFF 資訊架構](diagrams/export/ia-liff.svg)

```text
/liff/
├─ /elders/:elderId/schedules
└─ /elders/:elderId/health-report
```

- 根頁同時承擔長輩清單與新增長輩。`已實作`
- 兩個資源頁都有「返回長輩清單」的樹狀返回。`已實作`
- LIFF 已凍結維運；本階段只定義結構與 P0／P1 可用性基線，不導入最終品牌風格。`已決議`
- 每日摘要未提供 LIFF 入口。`已決議＋已實作`

## 6. Admin

![Admin 資訊架構](diagrams/export/ia-admin.svg)

```text
/admin/
├─ /messages
├─ /elders
│  └─ /elders/:elderId
│     ├─ 時間軸
│     ├─ 提醒設定
│     ├─ 記憶與摘要
│     ├─ 帳號與綁定
│     └─ 危急通知
├─ /news
├─ /system
└─ /traces/:traceId
```

### 排查主路徑

```text
總覽異常
→ 訊息流或長輩清單
→ 長輩單日時間軸
→ Trace 詳情
→ 第一個失敗階段
```

- Trace 顯示 Webhook、ASR、RAG、風險、LLM、TTS、回覆；不能只用「五階段」簡化現況。`已實作`
- 長輩詳情五分頁目前以一般 button 實作；資訊架構成立，但互動語意需補 tab 模式。`已實作`
- 策略檢視／撤銷沒有前端 route 或 API client；不在本次 IA 靜默增加第八頁。`已實作＋待決策`

## 7. 頁面與 API 對應

![頁面與 API 對應圖](diagrams/export/ia-page-api-mapping.svg)

| 頁面群 | 主要 client 函式 | API 資源概念 | 認證 |
| --- | --- | --- | --- |
| 家屬註冊／登入 | `registerGuardian`、`loginGuardian` | guardian sessions | 無 → Guardian Bearer |
| 長輩綁定／登入 | `bindElderDevice`、`loginElder` | device-bindings、elder sessions | 無 → Elder Bearer |
| 長輩對話 | `createTalkSocket`、`postTurn` 降級 | ws/talk、turns | Elder Bearer |
| 長輩提醒 | `listElderNotifications` | elder-notifications | Elder Bearer |
| 家屬首頁 | `listElders`、`createElder`、`listNotifications` | elders、notifications | Guardian Bearer |
| 長輩詳情 | `getHealthReport`、`listDailySummaries`、`listSchedules` | reports、summaries、schedules | Guardian Bearer |
| 協作與帳密 | `createGuardianInvite`、`setElderAccount` | guardian invites、elder account | Guardian Bearer |
| 統一行程管理 | `createSchedule`、`updateSchedule`、`deleteSchedule` | schedules | Guardian Bearer／LIFF idToken |
| Admin 總覽／訊息 | `getOverview`、`listMessages` | admin overview、messages | X-Admin-Key |
| Admin 長輩／trace | `listElders`、`getTimeline`、`getTrace` | admin elders、timeline、traces | X-Admin-Key |
| Admin 詳情分頁 | `getElderReminders`、`getElderMemory`、`getElderAccount`、`listElderRiskNotifications` | reminders、memory、account、risk notifications | X-Admin-Key |
| Admin 話題新聞 | `listNews` | admin/news | X-Admin-Key |
| Admin 系統 | `listJobs`、`getRagStatus`、`runJob` | jobs、RAG status | X-Admin-Key |

函式名稱以目前 client 為準；完整型別見 `shared/types.ts`。`已實作`

## 8. 角色與認證邊界

![角色與認證邊界圖](diagrams/export/ia-auth-boundaries.svg)

| 邊界 | 正常狀態 | 認證失敗 | UX 回復 |
| --- | --- | --- | --- |
| Expo Elder | Bearer Elder Session | 401 清 Session；對話 403 代表綁定失效 | 說明原因後提供帳密重登或重新綁定 |
| Expo Guardian | Bearer Guardian Session | 401 清目前角色 Session | 返回家屬登入，保留可理解原因 |
| LIFF Guardian | LINE idToken | 初始化或 API error | 提供重新開啟 LIFF；不可只顯示「稍後再試」 |
| Admin | X-Admin-Key | 401 清 localStorage key | 返回可見 label 的金鑰輸入表單 |

### 隱私界線

| 資訊 | 長輩 | 家屬 | Admin |
| --- | --- | --- | --- |
| 當輪系統回覆 | 可見／可聽 | 不適用 | 可觀測 |
| 每日摘要 | 目前長輩 UI 無入口 | 可見 | 可見 |
| 完整逐字稿 | 本人只在互動脈絡 | 不可見 | 內測可見 |
| 用藥／回診 | 目前不管理 | 可管理 | 可觀測 |
| 提醒／危急通知 | 長輩可讀自己的提醒內容（API 未分類嚴重度） | 可見 | 可觀測送達 |

## 9. IA 差異與待確認

1. `progress.md` 的 Admin 四頁是舊快照；本 IA 以七路由和五分頁現況為準。`已實作`
2. App client 有 `revokeElderDevice`，但目前頁面沒有對應操作。是否在家屬詳情提供「解除長輩裝置」需另行決策。`待決策`
3. 後端有全裝置登出與長輩 profile 更新能力，但現有 App／LIFF 沒有對應 UI。`待決策`
4. 通知若要支援類型、嚴重度、單筆已讀與跨裝置同步，需要先決定資料契約。`待決策`
5. Admin 共用金鑰沒有角色細分與人員別稽核；這是治理議題，不由線框圖自行擴張。`待決策`
