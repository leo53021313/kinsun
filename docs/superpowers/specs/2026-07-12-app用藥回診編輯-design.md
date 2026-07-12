# App 家屬端用藥／回診編輯 設計文件

- **日期**：2026-07-12
- **狀態**：Leo 已核准（畫面形式＝獨立管理頁、日期輸入＝原生日期選擇器，2026-07-12 問答拍板）
- **背景**：App 家屬端長輩詳情頁的「固定用藥」「即將回診」目前唯讀，新增與編輯須走 LINE 端（LIFF）。
  此為 [app/README.md](../../../app/README.md)「已知限制（MVP）」明列的缺口之一。

## 1. 目標與範圍

**目標**：家屬在 App 內完成用藥與回診的新增／編輯／刪除，不再依賴 LINE 端。

**範圍內**：

- App 前端：用藥管理頁、回診管理頁、詳情頁管理入口、api.ts 呼叫端 6 函式。
- 新增依賴：`@react-native-community/datetimepicker`（Expo Go 內建支援，`npx expo install` 裝相容版）。
- 文件：app/README.md 已知限制、docs/dev 12／16／17 回填。

**範圍外**（YAGNI）：

- 後端零改動——CRUD 端點已存在（[medications.py](../../../src/kinsun/web/routers/medications.py)、
  [appointments.py](../../../src/kinsun/web/routers/appointments.py)），家屬 token 認證與 App 現行呼叫同一套。
- LIFF 端不動（凍結中，功能照舊）。
- 回診「時刻」欄位（庚-15 另案）、字串常數集中（庚-31 另案）、App 測試基建（見 §6）。

## 2. 架構決策

| 決策 | 選擇 | 理由 |
| :--- | :--- | :--- |
| 畫面形式 | 獨立管理頁（詳情頁加「管理」按鈕跳轉） | 詳情頁已 6 區塊，保持乾淨；檔案小好維護；與 LIFF 頁面結構一致。備選「原地展開」因頁面過長被否決 |
| 日期輸入 | `@react-native-community/datetimepicker` | Leo 拍板：體驗優先，Expo Go 內建支援故成本低。備選「文字輸入零依賴」被否決 |
| 詳情頁重載 | `useEffect` 改 expo-router `useFocusEffect` | 從管理頁返回時自動重載，否則顯示舊資料 |
| 路由結構 | `[elderId].tsx` 轉 `[elderId]/` 目錄（index＋兩子頁） | expo-router 檔案式路由的巢狀慣例 |

## 3. 檔案清單

| 動作 | 檔案 | 職責 |
| :--- | :--- | :--- |
| git mv＋改 | `app/src/app/guardian/elder/[elderId].tsx` → `[elderId]/index.tsx` | 詳情頁：用藥／回診區塊各加「管理」按鈕；`useFocusEffect` 重載；時段字典改自 lib 匯入 |
| 新增 | `app/src/app/guardian/elder/[elderId]/medications.tsx` | 用藥管理頁（清單＋編輯／刪除＋表單） |
| 新增 | `app/src/app/guardian/elder/[elderId]/appointments.tsx` | 回診管理頁（同構） |
| 新增 | `app/src/lib/medicationSlots.ts` | 時段字典 `SLOTS`／`slotLabel`（自詳情頁抽出，比照 LIFF 同名檔） |
| 改 | `app/src/lib/api.ts` | 加 6 個 CRUD 函式 |
| 改 | `app/src/app/_layout.tsx` | screen 名改 `[elderId]/index`＋登記兩新頁（標題「用藥管理」「回診管理」） |
| 改 | `app/package.json` | 新增 datetimepicker 依賴 |

## 4. API 呼叫端（對接既有端點，統一信封＋snake_case）

| 函式 | 方法與路徑 |
| :--- | :--- |
| `createMedication(elderId, name, slots, token)` | `POST /api/v1/elders/{elder_id}/medications` |
| `updateMedication(elderId, medicationId, name, slots, token)` | `PUT …/medications/{medication_id}` |
| `deleteMedication(elderId, medicationId, token)` | `DELETE …/medications/{medication_id}`（204） |
| `createAppointment(elderId, date, label, token)` | `POST /api/v1/elders/{elder_id}/appointments` |
| `updateAppointment(elderId, appointmentId, date, label, token)` | `PUT …/appointments/{appointment_id}` |
| `deleteAppointment(elderId, appointmentId, token)` | `DELETE …/appointments/{appointment_id}`（204） |

命名依 AGENTS.md：HTTP 層建立用 `create*`、刪除用 `delete*`（camelCase 前端慣例，與既有 `createElder` 一致）。

## 5. 行為規格（兩頁同構，比照 LIFF）

- **清單**：每筆顯示內容（用藥＝名稱＋時段中文；回診＝日期＋內容），附「編輯」「刪除」outline 按鈕。
  空清單顯示 `EmptyHint`。
- **表單**（清單下方同頁）：
  - 用藥：藥名 `Field`＋時段多選 chips（早上／中午／晚上／睡前，`Pressable` 實作，選中填色）。
  - 回診：日期欄（點擊開 `DateTimePicker`，`mode="date"`、`minimumDate=今天`、iOS `display="inline"`、
    Android 預設 dialog；`event.type === "set"` 才取值，選後即關）＋內容 `Field`
    （placeholder 比照 LIFF：「例：上午10點 心臟科回診 林口長庚」）。
  - 預設為「新增」；點清單「編輯」帶入該筆轉更新模式，按鈕變「更新」並多「取消編輯」。
- **刪除**：`Alert.alert` 確認框（「確定要刪除『{名稱}』嗎？」，取消／刪除-destructive）。
- **前端驗證**：用藥＝藥名非空＋至少一時段；回診＝日期與內容非空。不足時就地顯示提示、不送出。
- **錯誤處理**：後端錯誤（`invalid_slot`、`date_in_past` 等）經統一信封繁中訊息以 `ErrorText` 顯示；
  網路失敗顯示通用「儲存失敗，請稍後再試」。
- **成功後**：重載清單、清空表單、退出編輯模式。
- **日期字串**：以本地時區組 `YYYY-MM-DD`（不用 `toISOString`，避免 UTC 位移跨日）。

## 6. 測試與驗證

App 專案無測試基建（CI 的 app job 僅 `tsc`，既有九畫面皆無單元測試）——遵循既有慣例，不在本工項建測試框架：

1. `npm run typecheck`（每步後必跑，CI 同款門檻）。
2. Expo Go 實機人工驗證清單：
   - [ ] 用藥：新增（多時段）→ 清單即現 → 編輯改時段 → 刪除（確認框）→ 詳情頁返回即更新
   - [ ] 回診：新增（日期選擇器擋過去日期）→ 編輯 → 刪除 → 詳情頁返回即更新
   - [ ] 錯誤路徑：空藥名／無時段／空內容被前端擋；後端 400 訊息正確顯示
   - [ ] iOS 與 Android 日期選擇器各驗一輪
3. 後端不動：既有 pytest 全套不受影響（不重跑）。

## 7. 風險

| 風險 | 對策 |
| :--- | :--- |
| datetimepicker 在 Expo Go 的版本相容 | 用 `npx expo install` 由 Expo 選版；SDK 57 官方支援清單內 |
| 路由改名（`[elderId]` → `[elderId]/index`）漏改 | `_layout.tsx` 同 commit 更新；typecheck＋實機導覽驗證 |
| iOS／Android picker 行為差異 | 統一「`set` 才取值、onChange 即關」模式，兩平台實機各驗 |
