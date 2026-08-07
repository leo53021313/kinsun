# 金孫 App（Expo，家屬端＋長輩端）

單一程式碼庫、一個 App 兩種角色：家屬帳密登入進管理介面；長輩輸入綁定碼進對講機介面。

## 開發上手（Expo Go，免 Mac、免簽章）

1. 手機安裝「Expo Go」（App Store／Play 商店，免費）。
2. 後端跑起來並對外（DGX 上的 kinsun 服務，開發常用 ngrok）。
3. 設定 API 位址：`cp .env.example .env`，填 `EXPO_PUBLIC_API_URL=https://xxxx.ngrok-free.app`。
4. `npm install`（首次）。
5. 啟動 dev server（DGX 上的常用做法）：`scripts/kinsun.sh start app`
   —— **預設走 tunnel**，手機在任何網路都連得到，不必和 DGX 同一個 Wi-Fi。
6. `scripts/kinsun.sh status` 的 `app` 那列直接給你 Expo Go 要掃的位址，形如
   `exp://xxx-anonymous-8081.exp.direct`（背景啟動時 Expo 不印 QR code，故由腳本問 Metro 取得）。
   手機掃它即可：iOS 用相機、Android 用 Expo Go 內建掃碼。

其他常用指令：

| 指令 | 用途 |
| :--- | :--- |
| `scripts/kinsun.sh restart app` | 重啟（改了原生設定、或 tunnel 斷線時） |
| `scripts/kinsun.sh stop app` | 停止 |
| `KINSUN_EXPO_TUNNEL=0 scripts/kinsun.sh restart app` | 改走區網（**僅限手機與 DGX 同網段**，啟動較快） |
| `npx expo start`（在 `app/`） | 不經腳本、單獨起，掃終端機印出的 QR code |

> `exp.direct`（Expo 的 tunnel 服務）偶爾會 `remote gone away` 起不來，腳本已內建自動重試一次。
> 若兩次都失敗，稍後再 `restart app` 即可。

## 角色測試流程（不再需要兩個 LINE 帳號）

1. 測試機 A：「我是家屬」→ 註冊（任意 email）→ 建立長輩 → 畫面顯示**長輩綁定碼**。
2. 測試機 B：「我是長輩」→ 輸入綁定碼 → 進對講機：可**按住說話、放開送出**，或**按一下開始、說完再按一下送出**，
   金孫回覆會放大顯示並自動播放語音。
3. 家屬機點長輩進詳情：健康報告（近 30 天危急事件）、每日摘要、用藥與回診
   （點「管理」可新增／編輯／刪除）、產生家屬邀請碼。

## 結構

- `src/app/`：expo-router 檔案式路由（`role`／`auth/*`／`guardian/*` Tabs／`guardian-detail/*` 深頁／`elder/*`）
- `src/lib/`：`api.ts`（後端呼叫，欄位 snake_case 與後端一致）、`auth.ts`（secure-store 存 token）、`theme.ts`、`todayLog.ts`
- `src/components/`：共用 UI、固定角色舞台 `BearStage` 與離線 `OttoBearRenderer`

## 已知限制（MVP）

- Expo Go 無法驗證遠端推播；需使用具平台推播憑證的 EAS development build 或正式版本驗收。
