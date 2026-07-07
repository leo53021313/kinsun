# 金孫 App（Expo，家屬端＋長輩端）

單一程式碼庫、一個 App 兩種角色：家屬帳密登入進管理介面；長輩輸入綁定碼進對講機介面。

## 開發上手（Expo Go，免 Mac、免簽章）

1. 手機安裝「Expo Go」（App Store／Play 商店，免費）。
2. 後端跑起來並對外（DGX 上的 kinsun 服務，開發常用 ngrok）。
3. 設定 API 位址：`cp .env.example .env`，填 `EXPO_PUBLIC_API_URL=https://xxxx.ngrok-free.app`。
4. `npm install`（首次）→ `npx expo start`。
5. 手機掃終端機的 QR code（iOS 用相機、Android 用 Expo Go 內掃碼）；電腦與手機需同網段，
   不同網段改跑 `npx expo start --tunnel`。

## 角色測試流程（不再需要兩個 LINE 帳號）

1. 測試機 A：「我是家屬」→ 註冊（任意 email）→ 建立長輩 → 畫面顯示**長輩綁定碼**。
2. 測試機 B：「我是長輩」→ 輸入綁定碼 → 進對講機：**按住說話、放開送出**，
   金孫回覆會放大顯示並自動播放語音。
3. 家屬機點長輩進詳情：健康報告（近 30 天危急事件）、用藥、回診、產生家屬邀請碼。

## 結構

- `src/app/`：expo-router 檔案式路由（`role`／`guardian/*`／`elder/*`）
- `src/lib/`：`api.ts`（後端呼叫，欄位 snake_case 與後端一致）、`auth.ts`（secure-store 存 token）、`theme.ts`
- `src/components/`：共用 UI 與 `AvatarPlaceholder`（虛擬形象預留區，日後換 Rive／Live2D 不動版面）

## 已知限制（MVP）

- 推播通知未接（規劃階段 5：Apple Developer 帳號＋EAS dev build）。
- 用藥／回診在 App 端目前唯讀，編輯先走 LINE 端；App 版編輯後續補。
