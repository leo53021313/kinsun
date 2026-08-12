# Kinsun Repo UX Audit

> 版本：v1.2｜日期：2026-07-30｜狀態：第一、第二階段評審稿；已依 main 同步後程式重驗路由、對講機與無障礙現況
> 範圍：Expo App、LIFF、Admin；以程式碼為 as-is 事實，以已拍板決策為產品意圖。

## 1. 稽核方法與證據等級

本次交叉檢查：

1. `AGENTS.md`、`README.md`、`progress.md` 與 `docs/dev/`。
2. Expo Router 實際檔案、React／React Native 頁面與元件。
3. 三端 API client、`shared/` 型別與認證標頭。
4. 現有 Token、硬編碼樣式、載入、錯誤、空狀態與權限流程。
5. App／LIFF／Admin 建置，以及環境可達的實際執行畫面。

本文使用以下標籤：

| 標籤 | 定義 |
| --- | --- |
| `已實作` | 可由目前程式碼、建置或執行畫面驗證。 |
| `已決議` | 決策文件已拍板，但不等於每個互動細節均已實作。 |
| `文件規劃` | 文件描述的未來或待辦內容。 |
| `推論` | 由現況推導，尚未經真實使用者驗證。 |
| `待研究` | 必須以長輩、家屬或維運人員研究驗證。 |
| `待決策` | 涉及產品、資料契約或跨團隊取捨，需團隊拍板。 |

## 2. Repo 與工作範圍現況

- 開工分支：`Jerry`。`已實作`
- 2026-07-30 已將最新 `origin/main` fast-forward 同步進 `Jerry`，並重驗三端路由；未改寫歷史、未 commit、未 push、未建立 PR。`已實作`
- 正式 App 的核准 Prototype 視覺、長輩提醒入口與 WS 狀態收尾已在目前工作樹整合；後端 API 與資料庫結構不在本輪修改範圍。`已實作`

主要前端結構：

```text
app/src/
├─ app/                    Expo Router 頁面
├─ components/             共用 React Native 元件
└─ lib/                    API、Session、字串、定位、Token
frontend/src/
├─ pages/                  LIFF 頁面
├─ admin/                  Admin 殼層、API、樣式、hooks
└─ admin/pages/            Admin 頁面與長輩詳情分頁
shared/
├─ client.ts               三端共用 API client 工廠
├─ envelope.ts             統一信封與 ApiError
├─ types.ts                三端共用資料型別
├─ terms.ts                等級與時段用語
└─ format.ts               日期時間與延遲格式
```

## 3. 三端前端現況

### 3.1 Expo App

| 項目 | 稽核結果 | 證據 |
| --- | --- | --- |
| 技術棧 | Expo SDK 54、React 19、React Native 0.81、Expo Router 6、TypeScript；`SecureStore` 保存 Session。 | `app/package.json:7-26`、`app/src/lib/auth.ts:32-72` |
| 實際頁面 | 12 頁，不含 `_layout.tsx`。 | `app/src/app/` 實際檔案 |
| 導覽 | 檔案路由；啟動頁依 active role 導向；角色頁分長輩／家屬。 | `app/src/app/index.tsx:9-25`、`app/src/app/role.tsx` |
| Session | 長輩與家屬各一個 slot；active role 另存；可切換另一個既有 Session。 | `app/src/lib/auth.ts:8-72`、`app/src/lib/SessionProvider.tsx:50-105` |
| 認證 | API 以 `Authorization: Bearer <token>`。 | `app/src/lib/api.ts:42-62` |
| 主要 API | 家屬註冊／登入、長輩綁定／登入、WS 語音 turn（POST 降級）、長輩、邀請、帳密代辦、摘要、報告、統一行程、家屬通知、長輩提醒。 | `app/src/lib/api.ts`、`app/src/lib/talkSocket.ts` |
| UI 元件 | `Button`、`Field`、`ErrorText`、`Section`、`EmptyHint`、A-Kin `AvatarPlaceholder`、`MicIcon`、`BellIcon`、`RoleSwitcher`。 | `app/src/components/` exports |
| Token | 9 個目前色彩、長輩字級 22／30／40、間距 4／8／16／24／40。 | `app/src/lib/theme.ts:3-22` |
| 狀態 | 頁面各自管理 loading／error／empty；缺少一致的狀態元件與可公告語意。 | `app/src/app/**` |

實際路由：

```text
/
/role
/elder/bind
/elder/login
/elder/talk
/elder/notifications
/guardian/login
/guardian/register
/guardian/home
/guardian/elder/:elderId
/guardian/elder/:elderId/schedules
/guardian/notifications
```

### 3.2 LIFF

| 項目 | 稽核結果 | 證據 |
| --- | --- | --- |
| 技術棧 | React 19.2、Vite 6、React Router 8、TypeScript。 | `frontend/package.json` |
| 實際頁面 | 3 頁：長輩清單、統一行程、健康報告。 | `frontend/src/App.tsx` |
| 導覽 | `/liff` basename；清單為根，兩個長輩子頁以明確返回連結回清單。 | `frontend/src/App.tsx`、`frontend/src/pages/` |
| 認證 | LIFF 初始化後取得 LINE idToken，作為 Bearer token。 | `frontend/src/App.tsx:11-31`、`frontend/src/api.ts:24-29` |
| 主要 API | 長輩清單／新增、家屬邀請、統一行程 CRUD、健康報告。 | `frontend/src/api.ts` |
| 視覺 | 沒有產品 CSS 匯入，執行時主要為瀏覽器預設樣式。 | `frontend/src/main.tsx`、執行截圖 |
| 狀態 | 部分 loading／error 存在；表單缺一致 busy、刪除確認、欄位 label 與回復路徑。 | `frontend/src/pages/` |

實際路由：

```text
/liff/
/liff/elders/:elderId/schedules
/liff/elders/:elderId/health-report
```

### 3.3 Admin

| 項目 | 稽核結果 | 證據 |
| --- | --- | --- |
| 技術棧 | React 19.2、Vite 6、React Router 8、獨立 `admin.css`。 | `frontend/package.json`、`frontend/src/admin/main.tsx` |
| 實際頁面 | 7 個路由；長輩詳情內含 5 個分頁，不另算路由。 | `frontend/src/admin/App.tsx`、`ElderDetailPage.tsx` |
| 導覽 | 頂部主導航：總覽、訊息流、長輩、新聞、系統；trace 為第三層。 | `frontend/src/admin/App.tsx` |
| 認證 | `X-Admin-Key` 存在 `localStorage`；401 清除並回金鑰表單。 | `frontend/src/admin/api.ts:47-84` |
| 主要 API | overview、messages、elders、timeline、trace、reminders、memory、account、risk notifications、jobs、RAG status。 | `frontend/src/admin/api.ts:86-160` |
| 狀態 | `useLoadable`、`usePolling` 已共用；仍有首次空陣列與真正空狀態難區分的頁面。 | `frontend/src/admin/useLoadable.ts`、`MessagesPage.tsx` |
| 無障礙 | HTML 原生元素提供部分基礎語意；分頁未使用 tab 語意，焦點樣式與 key input label 不完整。 | `frontend/src/admin/App.tsx:13-34`、`ElderDetailPage.tsx` |

實際路由：

```text
/admin/
/admin/messages
/admin/elders
/admin/elders/:elderId
/admin/traces/:traceId
/admin/news
/admin/system
```

長輩詳情五分頁：時間軸、提醒設定、記憶與摘要、帳號與綁定、危急通知。`已實作`

## 4. 共用資料與隱私邊界

- 三端使用 `createApiClient` 解包 `{success, data, error, meta}`，錯誤轉為 `ApiError`。`已實作`（`shared/client.ts:24-51`、`shared/envelope.ts:8-29`）
- `Elder`、`ScheduleGroup`、`HealthReport`、`DailySummary`、Admin trace 等型別集中於 `shared/types.ts`。`已實作`
- 家屬可看危急事件、提醒與每日摘要，但不可看完整逐字對話；Admin 現階段可看完整內容。`已決議`（`docs/dev/00_決策清單.md:79-85`）
- App 通知型別目前只有 `content`、`created_at`；沒有 `kind`、嚴重度、notification id 或後端已讀欄位。`已實作`（`shared/types.ts:18`）
- 因此，本階段線框中的「危急／提醒／單筆已讀」是資訊呈現提案，均標記 `待決策`，不得當成已存在的 API 能力。

## 5. 現有元件、Token 與狀態實作

### 5.1 可重用項目

- `Button` 已有 `busy`、`disabled` 與 48pt 最小高度。`已實作`
- `Field`、`ErrorText`、`Section`、`EmptyHint` 已減少頁面重複樣式。`已實作`
- `MicIcon`／`BellIcon` 為向量圖示；`AvatarPlaceholder` 內部已載入正式 A-Kin 靜態插畫，支援 idle／listening／thinking／speaking／error 五態。`已實作`
- 統一行程頁支援吃藥／回診／其他三種類型；用藥時段與時間規則由 `lib/schedules.ts` 純函式驗證。`已實作`
- Admin 有 `useLoadable`、`usePolling`；三端字串分端集中。`已實作`

### 5.2 主要缺口

- `Field` 可見 label 與 `TextInput` 沒有明確程式化關聯。`已實作`
- `ErrorText` 沒有 alert／live region；動態錯誤可能不被 Screen Reader 即時讀到。`已實作`
- `Section` 標題沒有 heading 語意。`已實作`
- `Button busy` 以 spinner 取代文字，缺少明確的「處理中」可存取名稱與狀態。`已實作`
- 對話狀態帶已有 `accessibilityLiveRegion`，但尚未以 VoiceOver／TalkBack 完整實機驗證公告節奏與重複讀取。`已實作＋待研究`
- App 日期控制與時段 Chip 的視覺高度有低於 48pt 的風險；`RoleSwitcher` 也不是長輩友善的主操作尺寸。`推論`
- Web／Admin 樣式沒有共享 foundation；LIFF 幾乎完全未設計。`已實作`

目前 `theme.ts` 的暖磚橘、米色背景、圓角與字級只在本文件中稱為「目前實作值」，不是最終品牌決策。

## 6. 載入、錯誤、空狀態與權限

| 區域 | 已有 | UX 缺口 |
| --- | --- | --- |
| 啟動 | Session loading spinner。 | Expo Web 的歷史 SecureStore 錯誤不代表 native；Android Expo Go 另依 `app/design-qa.md` 驗證。 |
| 長輩綁定 | 相機權限、QR、手動碼、後端錯誤訊息。 | 成功後立即導頁，成功回饋不可感知；無權限時缺清楚「開設定」與手動替代層級。 |
| 長輩對話 | Idle／Listening／Thinking／Speaking／Error、A-Kin、鈴鐺未讀 badge、觸覺、結束音效、回覆 ScrollView；WS ack／reply 依序播放，純文字 reply 直接收尾，未連線退回 POST；狀態帶有 live region。 | 首次進入立即連續請求麥克風與定位；麥克風拒絕缺設定 CTA；403 訊息可能因 sign-out 導頁而消失；live region 尚未經 VoiceOver／TalkBack 完整實機驗證。 |
| 家屬首頁 | 長輩列表、空提示、API error、通知 badge。 | `elders` 初始為空陣列，首次載入可能被當成真正空狀態；錯誤沒有顯性重試。 |
| 長輩詳情 | report、summary、schedules 區塊。 | `Promise.all` 造成單一 API 失敗可能拖垮整批；部分區塊在尚未載入時可能顯示空。 |
| 統一行程 | loading、空、清單、三類表單、系統刪除確認、API error。 | 沒有成功 banner／live announcement；表單缺 KeyboardAvoiding 策略。 |
| 通知 | loading gate、空狀態、本機已讀水位。 | 資料契約無類別／嚴重度／單筆已讀，不能可靠呈現危急與提醒差異。 |
| LIFF | 文字 loading／error。 | 缺結構化空狀態、忙碌狀態、欄位 label、刪除確認與一致回復。 |
| Admin | loading、error banner、polling disconnect、load older。 | 首次空陣列與真正空清單可能混淆；tab 語意、焦點、重新驗證入口不足。 |

## 7. 文件與程式碼差異

| 項目 | 文件描述 | 程式碼現況 | 是否一致 | UX 影響 | 建議處理 |
| --- | --- | --- | --- | --- | --- |
| 頁面數 | `docs/dev/17`：App 12、LIFF 3、Admin 7。 | 路由實查為 12／3／7。 | 是 | 可作本次盤點基準。 | 維持，新增路由時同步文件。 |
| UI atom 無障礙 | `docs/dev/12` 記錄長輩主要控制與對話狀態語意。 | 對話頁已有 role、state 與 live region；共用 Field、Error、Section 仍缺完整語意。 | 部分 | Screen Reader 對表單與共用訊息仍可能理解不完整。 | 把「對話頁已實作」與「共用元件語意待補」分開追蹤。 |
| 403 回復 | `docs/dev/17`：清 Session 並引導重綁。 | `talk.tsx` 設 reply 後立即 `signOut()`，路由 guard 可能先導離。 | 部分 | 長輩可能看不到原因與下一步。 | 以可持續的回復原因或專用狀態頁承接。 |
| Admin 頁數 | `progress.md` 仍記錄早期四頁。 | 現況為七路由＋長輩詳情五分頁。 | 否 | 新成員可能漏測新聞、系統與分頁。 | 把 `progress.md` 視為時間快照；以 docs/dev 與程式碼為準。 |
| LIFF 視覺 | 文件稱維持極簡並於 App 定稿後跟進。 | 幾乎是瀏覽器預設樣式。 | 是，但品質未完成 | 基本表單與狀態的可用性仍不足。 | 凍結期間至少修正 P0／P1 無障礙，不需品牌化。 |
| 通知呈現 | 產品意圖需危急通知、提醒與未讀。 | `AppNotification` 只有內容與時間；已讀是本機 waterline。 | 部分 | 無法可靠分類、同步或單筆標示。 | `待決策` 通知資料契約，再做視覺層級。 |
| Admin 策略管理 | 工作拆解／後端已有策略相關能力描述。 | 前端無策略 route、client 或頁面。 | 否 | 不應在 IA 靜默增加第八頁。 | 團隊決定是否納入後續 Admin 範圍。 |
| Admin dev 入口 | 應可由 Vite 開發伺服器啟動。 | `frontend/admin/index.html` 在本次 dev server 解析 `/src/admin/main.tsx` 時 404；production build 可成功。 | 否 | 開發期視覺驗證會看到空白。 | 另開工程任務修正 dev base／root；本次不改產品設定。 |
| Expo Web | App 可由 Expo 啟動。 | Web bundle 在 `SecureStore.getItemAsync` migration 發生 runtime error。 | 否（僅 Web） | 本次無法以 Web 完成 App 動態稽核。 | Native 為主目標；若要支援 Web，需明確 adapter／fallback。 |

## 8. 重要 UX 發現與優先序

| 優先級 | 發現 | 證據 | 影響 |
| --- | --- | --- | --- |
| P0 | 家屬資訊架構必須持續排除完整逐字對話。 | `已決議` | 隱私與同意風險。 |
| P0 | 通知資料不足以可靠表達危急／提醒／單筆已讀；不得只靠文案猜測。 | `已實作` | 可能誤判事件嚴重程度。 |
| P0 | 403 sign-out 後原因與重綁下一步可能消失。 | `已實作＋推論` | 長輩無法恢復核心任務。 |
| P1 | 麥克風拒絕只有文字，缺開設定與重新檢查。 | `已實作` | 無法開始核心語音任務。 |
| P1 | 對話動態狀態已加入 live region，但尚未以 VoiceOver／TalkBack 完整實機走完錄音、等待、播放與錯誤。 | `已實作＋待研究` | 尚不能確認公告時機、重複讀取與整輪任務可完成性。 |
| P1 | 家屬首頁／詳情的「尚未載入」與「真的沒有資料」有混淆風險。 | `已實作＋推論` | 造成不信任與誤判。 |
| P1 | 詳情頁並行資料沒有局部失敗隔離。 | `已實作` | 一個 API 失敗掩蓋其他可用資訊。 |
| P1 | LIFF 缺表單 label、busy、刪除確認與完整狀態。 | `已實作` | 鍵盤與輔助科技使用困難。 |
| P1 | Admin tabs 未使用 tab 語意與鍵盤模式。 | `已實作` | 鍵盤與 Screen Reader 導覽不清。 |
| P2 | 現有硬編碼尺寸、圓角、字級與 Web CSS 尚未收斂為跨端 foundation。 | `已實作` | 後續視覺一致性與維護成本上升。 |

## 9. 執行畫面證據

### Admin 金鑰輸入

![Admin 金鑰輸入](repo-audit-screenshots/01-admin-key-entry.png)

### Admin 後端未連線

![Admin 總覽連線中斷](repo-audit-screenshots/02-admin-overview-disconnected.png)

### LIFF 初始化失敗

![LIFF 初始化失敗](repo-audit-screenshots/03-liff-initialization-error.png)

### Expo Web SecureStore runtime error

![Expo Web SecureStore 錯誤](repo-audit-screenshots/04-expo-web-secure-store-error.png)

上述畫面是本次稽核環境證據，不是線框圖或最終視覺設計。Admin 與 LIFF 缺少後端／有效 LIFF 環境，所以只驗證到可達錯誤狀態；App Web 被 SecureStore runtime error 阻擋。`已實作`

## 10. 本階段結論

1. 12／3／7 頁架構與最新版 `docs/dev/17` 一致，可直接作 Phase 1 IA 基線。`已實作`
2. 長輩端應以「綁定／重登 → 權限 → 單一語音任務 → 可理解回復」為唯一主線。`推論`
3. 家屬端應以長輩為資訊主體，照護資料分區揭露，持續排除逐字對話。`已決議＋推論`
4. Admin 的主要排查路徑是「總覽 → 訊息或長輩 → 時間軸 → trace」；處理註記與人員別權限不在現有前端。`已實作`
5. 本套線框仍是灰階資訊與互動骨架；正式 `/elder/talk` 已另行採核准 Prototype 的暖色介面與 A-Kin 靜態插畫，兩者不可混稱。`已實作`
