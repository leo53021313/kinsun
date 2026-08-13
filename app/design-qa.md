# `/elder/talk` Prototype 視覺整合 QA

> 首次驗證：2026-07-28｜最近複驗：2026-07-30
> 範圍：正式 Expo 長輩對講機介面

## Findings

- P0／P1／P2：第二輪比對後無待修項目。
- P3：Android 系統狀態列、系統字型光學呈現與導覽列會和核准稿的 iPhone 模板略有差異。這是原生平台差異，不影響版面層級、可讀性或操作。
- P3：正式頁不保留 Prototype 專用的「示範連線錯誤」連結；正式錯誤狀態由實際請求失敗觸發。這是刻意的產品邊界。

## 2026-07-30 `main` 同步後複驗

- 分支：`Jerry`；同步基準：`a874056`。
- 裝置：`ExpoGo_Pixel_8_API_36`、Android 16／API 36、Expo Go 54.0.8。
- 顯示：模擬器覆寫為 1032×2237 px、420 dpi，約為 393×852 dp；系統字級 1.0。
- UI-QA 只暫時略過未登入導頁，未建立測試帳號、未寫入後端資料；複驗結束後已移除測試旁路。

| 狀態／檢查 | 結果 | 證據 |
| :--- | :--- | :--- |
| Idle | 通過；標題、56dp 鈴鐺、登出、A-Kin、狀態帶、回覆、104dp 麥克風與鍵下提示完整可見 | `qa/elder-talk-idle-android-393x852-main-sync.png` |
| 短按聆聽 | 通過；顯示「正在聽你說」與「說完再按一下」 | `qa/elder-talk-listening-tap-android-393x852-main-sync.png` |
| 送出／思考 | 通過；顯示「想一下喔」且主要按鈕呈停用狀態 | `qa/elder-talk-thinking-android-393x852-main-sync.png` |
| 受控錯誤 | 通過；無有效 QA Session 的送出安全落到「連線不太穩」與重新說明 | `qa/elder-talk-error-android-393x852-main-sync.png` |
| UI tree | 通過；鈴鐺 bounds 147×147 px＝56dp、麥克風 bounds 273×273 px＝104dp，鍵下提示底端 2104 小於 ScrollView 底端 2174 | Android UI hierarchy |
| 執行期錯誤 | 通過；上述互動後無 React Native JS error、Fatal Exception 或 AndroidRuntime Fatal | 清空後 logcat |

WebSocket `ack`／`reply` 的真實往返需要有效長輩 Session 與可用後端，本輪未把 UI-QA 誤列為端到端驗證；改由 `talkPresentation.test.ts` 驗證播放完成時的 `ack → thinking`、無分段的 `reply → idle`、有分段的 `reply → 等待續播`，以及訊框抵達時有音檔不搶先切態、無音檔 ack → thinking、純文字 reply → idle。完整 Jest 結果為 5 個套件、53 項測試全數通過。

## Open Questions

- 無阻擋交付的設計問題。iOS 實機的字型光學呈現與 Safe Area 尚未另做截圖比對，屬後續跨平台實機驗收範圍。

## 比對基準與正規化

- 核准來源：`../docs/uiux/prototype/qa/implementation-v2-idle.png`
- 原始視覺方向：`../docs/uiux/prototype/references/source-visual.png`
- 正式 A-Kin 資產：`assets/images/akin-hero.png`
- 正式 Android 截圖：`qa/elder-talk-idle-android-393x852.png`
- 完整並排比對：`qa/comparison-prototype-formal-idle-stacked.png`
- 比對狀態：Idle；同為亮色主題、已登入長輩對講機主頁。
- 來源像素：393×852 px。
- 實作原始像素：1032×2237 px；Android 模擬器以 420 dpi 覆寫成約 393×852 dp（密度約 2.625）。
- 實作比對像素：`qa/elder-talk-idle-android-normalized.png` 正規化為 393×852 px；原生截圖不使用瀏覽器 `deviceScaleFactor`。
- 未另做局部裁切比對：完整 393×852 比對已能清楚辨識關鍵文字、圖示、插畫邊緣與留白，並另以 UI tree bounds 驗證裁切風險。

## 必要視覺面檢查

| 面向 | 結果與證據 |
| :--- | :--- |
| 字型與排版 | 通過。維持系統字型與 elder 22pt 最小 token；標題、狀態、回覆、動作提示的字重與層級清楚，393×852 無截斷。平台字型差異列為 P3。 |
| 間距與版面節奏 | 通過。21dp 左右頁邊、A-Kin、狀態帶、回覆、104dp CTA 與鍵下提示均完整落在可捲動內容；第二輪已修正首輪裁切。 |
| 色彩與 token | 通過。`talkColors` 對應核准稿的紙白、藍、黃、珊瑚與深墨線條；狀態色有語意區隔，錯誤文字維持高對比。 |
| 圖像品質與資產忠實度 | 通過。直接使用核准的透明背景 A-Kin PNG，SHA-256 與 Prototype 資產一致；`expo-image` 以 contain 呈現，無拉伸、裁切、emoji 或程式繪圖替代。 |
| 文案與內容 | 通過。Idle、聆聽、思考、播放、錯誤與雙手勢動作提示均為台灣繁體中文，獨立閱讀可理解；Prototype 示範連結未帶入正式產品。 |
| 圖示與表面 | 通過。五態狀態與登出採 Phosphor 粗線圖示；麥克風主鍵與提醒鈴鐺沿用既有 `react-native-svg` 圖示。邊框、圓角、陰影與插畫式按壓回饋一致。 |
| 無障礙與韌性 | 通過。主要 CTA 104dp、登出 48dp；補 accessibility role／label／state／live region；全頁 ScrollView 支援較小裝置與系統大字。 |

## 狀態與互動驗證

| 狀態／流程 | 結果 | 證據 |
| :--- | :--- | :--- |
| Idle | 通過；A-Kin、狀態帶、回覆、104dp CTA 與動作提示皆完整可見 | `qa/elder-talk-idle-android-393x852.png` |
| 短按開始聆聽 | 通過；狀態改為「正在聽你說」，提示改為「說完再按一下」 | `qa/elder-talk-listening-tap-android-393x852.png` |
| 長按聆聽 | 通過；超過 500ms 後提示改為「放開送出」，放開後進送出流程 | `qa/elder-talk-listening-hold-android-393x852.png` |
| 受控錯誤 | 通過；本機 QA 未設定 API URL 時顯示「連線不太穩」與重新說明，沒有未處理例外 | `qa/elder-talk-error-android-393x852.png` |
| 登出取消 | 通過；顯示確認 Alert，取消後留在對講機頁 | Android UI 自動化＋清空後 logcat |

清空 logcat 後重跑短按、長按、受控錯誤與登出取消，未發現 App error。正式 auth、裝置 token、API、403、位置、錄音／播放與 `talkGesture` 雙手勢狀態機均未改寫。

## 比對迭代紀錄

1. 第一輪在 393×852 邏輯尺寸發現 P2：鍵下動作提示只剩 3 px 可見，UI tree bounds 為 `[127,2171][904,2174]`。
2. 修正：回覆字級由 30 調為 elder 最小 token 22、A-Kin 最大寬由 315 調為 285、主要垂直 gap 由 12 調為 10。
3. 第二輪：動作提示 bounds 為 `[127,2001][904,2083]`，完整落在 ScrollView 內容範圍 `[0,123][1032,2174]`；A-Kin、狀態帶、回覆與 CTA 亦全數可見。完整證據為 `qa/comparison-prototype-formal-idle-stacked.png`。

## Implementation Checklist

- [x] 核准 A-Kin 資產與正式 App 使用檔案一致。
- [x] 核准 Prototype 的插畫式層級與五態 presentation 已整合。
- [x] 393×852 Idle 全畫面第二輪比對無 P0／P1／P2。
- [x] 主要雙手勢、受控錯誤與登出取消已在 Android Expo Go 54 驗證。
- [x] 型別、Lint、單元測試、Expo Doctor 與 Android bundle export 通過。

## Follow-up Polish

- 若進入 iOS 實機驗收，再補同尺寸 iPhone Safe Area／系統字型截圖；只有發現可見漂移時才調整平台限定間距。

final result: passed
