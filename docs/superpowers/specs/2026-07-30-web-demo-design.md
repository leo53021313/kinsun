# 網頁版全功能前端（web/）設計

> **日期**：2026-07-30
> **狀態**：待 Leo 審查
> **目的**：把長輩端與家屬端的全部功能搬到一個網頁上，成為 App 凍結後**唯一還在演進的前端**。用於內部測試與畢業典禮對廠商的展示；開場先顯示運營狀態，可用才讓人進去，進場動畫由中央撕裂展開成左右雙欄。

---

## 1. 背景

`app/`（Expo）與 `frontend/`（LIFF）自本設計起**皆凍結**，往後所有前端展示由 `web/` 承擔。因此 `web/` 不是「demo」，它是產品的展示面，**功能必須與 App 完全對齊**。

受眾與使用場合明確：

- **內部測試**：七位組員各自登入自己的帳號，各測各的（記憶綁 `elder_id`，帳號分開＝記憶天然隔離）
- **畢業典禮**：組員代操、投影給廠商看。廠商不註冊帳號、不自己操作
- **結業後**：服務關閉，網址連不上即可，不需要優雅降級

開場的運營狀態頁因此有明確用途：**內部測試與展示當天，一眼看出哪個服務沒開**（忘記啟動 ASR、TTS 模型還在載入、排程器假死），而不是進去按了才發現對講機不動。

## 2. 目標

1. 長輩端 4 畫面、家屬端 6 畫面的**全部功能**在網頁上可正常操作（清單見 §5.4）
2. 開場運營狀態頁 → 撕裂展開動畫 → 左右雙欄（左長輩、右家屬）
3. 兩端在同一頁面上各自獨立登入，操作互相連動
4. 美術與版面全新設計，不受 React Native 樣式系統約束

### 非目標

- 離線示範模式——2026-07-30 Leo 決定不做（W-22）。展示當天若 DGX 或網路出狀況，沒有程式層的備案
- Web Push（系統級推播）——以畫面上的模擬通知橫幅取代
- 深色模式——維持 D-49「不做」的決議
- admin 觀測後台——內部維運工具，不納入
- landing page——以後另做
- 修改 `app/` 與 `frontend/`——兩者凍結

## 3. 決策紀錄

本節記錄 Leo 於 2026-07-30 對話中的決定，供後續施工與回溯依據。

| # | 決定 | 內容 |
| :-- | :--- | :--- |
| W-01 | 技術選型 | Vite + React（不做外殼包裝，不做單檔 HTML） |
| W-02 | 資料來源 | 接真後端（非假資料） |
| W-03 | 運營狀態 | 新增公開端點 `GET /api/v1/demo-status` |
| W-04 | 登入方式 | **兩欄各自登入各自的帳號**，不做自動登入的示範帳號（組員需各測各的） |
| W-05 | admin 後台 | 不納入 |
| W-06 | 兩端連動 | 要 |
| W-07 | `frontend/`（LIFF） | 不動 |
| W-08 | 版面 | 左右兩欄畫成手機外框 |
| W-09 | 窄螢幕 | 上下堆疊＋頂部角色頁籤 |
| W-10 | 深色模式 | 不做 |
| W-11 | 動畫無障礙降級 | 要（`prefers-reduced-motion`） |
| W-12 | 目錄與網址 | 目錄 `web/`，對外掛 `/demo`（未來 landing page 另做） |
| W-13 | 危急警報呈現 | 在兩端手機外框上**模擬** iOS／Android 系統通知橫幅。⚠️ 這是**前端呈現方式**的決定，不是要在後端加阻擋——本前端註冊的帳號無 LINE 綁定，真實外送本來就不會發生（詳見 §9） |
| W-14 | 系統級推播 | 同 W-13，不做 Web Push |
| W-15 | QR 掃碼 | 全瀏覽器支援（用 `zxing-wasm`，非 Chrome 專屬的 `BarcodeDetector`） |
| W-16 | 部署 | 靜態檔掛後端 `/demo`，經 ngrok 對外 |
| W-17 | 註冊政策 | 完全開放，不設通關密語 |
| W-18 | 樣式 | Tailwind CSS v4 |
| W-19 | 節流 | 放寬。只保留全域併發閘門與帳號級保險絲（見 §10 B2） |
| W-20 | 廠商入口 | 組員代操，廠商只看（因此不做示範帳號） |
| W-21 | 結業後 | 連不上就連不上，不做獨立主機的告示頁 |
| W-22 | 展示備案 | **不做**離線示範模式（2026-07-30 決定，先前一度核可、同日改回不做） |

## 4. 技術選型

| 層 | 選擇 | 版本 | 理由 |
| :-- | :--- | :--- | :--- |
| 建置 | Vite | 8.x | 現行主流。獨立 package，與 `frontend/`（Vite 6）互不牽制 |
| 框架 | React + TypeScript | React 19 | 與 `app/`（19.1）、`frontend/`（19.2）同代，`shared/` 型別直接共用 |
| 路由 | react-router | 8.x | 與 `frontend/` 同一套 |
| 樣式 | Tailwind CSS v4 | 4.x | W-18。`@theme` 沿用既有設計 token（9 色、22/30/40 字級、spacing 4/8/16/24/40） |
| 動畫 | 純 CSS（`clip-path`＋`transform`） | — | 撕裂展開用 CSS 足夠，不為單一動畫引入動畫函式庫 |
| QR 產生 | `qrcode` | 1.5.x | 家屬端顯示綁定 QR |
| QR 解碼 | `zxing-wasm` | 3.x | W-15。瀏覽器原生 `BarcodeDetector` 僅 Chrome 系支援 |
| 型別／API | 既有 `shared/` | — | `client.ts`／`types.ts`／`envelope.ts`／`format.ts`／`terms.ts` 直接引用 |
| 狀態 | React Context × 2 | — | 雙角色各一份，見 §7 |
| 測試 | Vitest + testing-library | — | 與 `frontend/` 同套 |

**依 AGENTS.md「除非有充分理由否則不新增第三方套件」，逐項理由**：

- **Tailwind CSS v4**：W-18 Leo 核定。全新美術需要快速迭代，樣式與標記同處一地可省下大量來回
- **`qrcode`**：家屬端要產生綁定 QR。QR 編碼含 Reed-Solomon 糾錯與版本／遮罩選擇，非自行實作的合理範圍
- **`zxing-wasm`**：長輩端要掃 QR。解碼涉及影像二值化、定位圖樣偵測與糾錯，更不可能自寫；瀏覽器原生的 `BarcodeDetector` 僅 Chrome 系支援，不符 W-15「全瀏覽器」

Vite／React／react-router／Vitest 屬既有技術棧（`frontend/` 已在用），不計為新增。

## 5. 三個階段

### 5.1 開場：運營狀態頁

進站呼叫 `GET /api/v1/demo-status`，中央一張狀態卡（整體狀態＋分項燈號），下方「開始使用」按鈕。每 10 秒自動重查——服務剛啟動或剛修好時，使用者不必手動重整。

判定規則：

| 整體狀態 | 條件 | 按鈕 |
| :--- | :--- | :--- |
| **可用** | 全部分項正常 | 亮，可點 |
| **部分受限** | TTS 異常（聽得懂但不會出聲）／排程器逾期（提醒不會響）／對話模型近期錯誤率偏高 | 可點，旁邊以白話標明缺什麼 |
| **停機** | 資料庫不通 **或** 語音辨識不通 | 灰，不可點 |

「語音辨識不通＝停機」是因為對講機是本產品的核心，ASR 掛掉時整個核心功能不存在，讓人進去只會得到壞掉的印象。

分項需能分辨「服務未啟動」與「模型載入中」（埠已開但 `/healthz` 未就緒）——這是內部測試最常遇到的狀態，`scripts/kinsun.sh` 的 `_health_note` 已有同樣的判斷，行為對齊。

### 5.2 撕裂展開動畫

點下「開始使用」→ 狀態卡與背景沿一道不規則裂痕分成左右兩半 → 各自往外滑開並微幅傾斜 → 後方雙欄舞台露出。

- 實作：兩層 `clip-path: polygon()` 各取一半（鋸齒頂點手工調校），加 `transform: translateX() rotate()`，700ms `cubic-bezier`
- **舞台在動畫期間就開始掛載與發請求**，不等動畫結束（否則平白多等 700ms）
- `prefers-reduced-motion: reduce` → 改為 200ms 淡入
- 動畫只播一次；直接開 `/demo/stage` 不播

### 5.3 雙欄舞台

- **寬螢幕（≥1024px）**：左右並排兩支手機外框。這是展示當天的主要形態（組員代操投影）
- **窄螢幕**：上下堆疊＋頂部「長輩／家屬」切換頁籤。組員自己拿手機測試時使用，功能完整但不做額外視覺投資
- **手機外框**：圓角、動態島、狀態列（時間／訊號／電量）、底部 home indicator。**外框頂部即模擬系統通知橫幅滑入的位置**
- 框內為各端完整畫面，有自己的內部導覽（不改動瀏覽器網址列）

### 5.4 路由與畫面清單

瀏覽器路由只有兩條——手機外框**內部**的畫面切換是元件狀態，不進網址列（否則兩欄會搶同一條網址）：

| 路由 | 內容 |
| :--- | :--- |
| `/demo` | 開場運營狀態頁 |
| `/demo/stage` | 雙欄舞台（直接開啟時不播撕裂動畫） |

框內畫面（與 `app/` 一對一對應，全部必須實作）：

| 端 | 畫面 | 對應 App 路由 | 主要功能 |
| :--- | :--- | :--- | :--- |
| 長輩 | 綁定 | `elder/bind` | 掃 QR ／ 手動輸入綁定碼 |
| 長輩 | 帳密重登 | `elder/login` | 手機號碼＋密碼（換機／登出後用） |
| 長輩 | 對講機 | `elder/talk` | 按住說話／短按切換兩種手勢、四種表情、字幕、分段語音續播、WS＋POST 降級、附帶模糊定位、未讀鈴鐺、登出 |
| 長輩 | 提醒列表 | `elder/notifications` | 用藥／回診提醒與主動關懷，開啟即更新已讀水位 |
| 家屬 | 註冊 | `guardian/register` | Email＋密碼＋姓名 |
| 家屬 | 登入 | `guardian/login` | Email＋密碼 |
| 家屬 | 首頁 | `guardian/home` | 長輩列表、新增長輩（綁定碼＋QR＋複製）、通知未讀 badge、登出 |
| 家屬 | 長輩詳情 | `guardian/elder/[elderId]` | 健康報告（危急事件分級）、每日摘要、排程摘要、代辦長輩帳密、家屬邀請碼 |
| 家屬 | 排程管理 | `guardian/elder/[elderId]/schedules` | 用藥／回診／自訂 × 一次／每日／每週 的新增、修改、刪除 |
| 家屬 | 通知列表 | `guardian/notifications` | 警報／提醒／關懷，開啟即更新已讀水位 |

`app/` 的 `role.tsx`（選身分）與 `RoleSwitcher`（內測切換身分）**不移植**——雙欄同時呈現兩種身分，這兩者失去意義。

## 6. 模組切分

```
web/
├─ index.html
├─ vite.config.ts          （含 dev 用的 /api proxy，比照 frontend/）
├─ tailwind.config / theme
└─ src/
   ├─ main.tsx / App.tsx    路由與階段
   ├─ gate/                 GatePage · StatusCard · useDemoStatus
   ├─ stage/                StagePage · TearTransition · PhoneFrame · NotificationBanner
   ├─ elder/                ElderApp · BindScreen · LoginScreen · TalkScreen
   │                        · NotificationsScreen · Avatar
   ├─ guardian/             GuardianApp · RegisterScreen · LoginScreen · HomeScreen
   │                        · ElderDetailScreen · SchedulesScreen · NotificationsScreen
   ├─ session/              createSessionContext(role) · storage
   ├─ talk/                 talkSocket · talkGesture · recorder · playback
   ├─ notify/               useNotificationFeed · bus
   ├─ api.ts                createApiClient（同源，不設 baseUrl）
   ├─ strings.ts            zh-TW 字串常數集中（沿用 D-50）
   └─ theme.css             Tailwind @theme：既有設計 token
```

檔案規模遵循 `.claude/rules/coding-style.md`：單檔 200～400 行為常態、800 行為上限。`app/src/app/elder/talk.tsx` 現為 542 行且職責混雜（權限、手勢、連線、播放、續播佇列全在一支元件裡），移植時拆為 `TalkScreen`（畫面與狀態）＋ `talk/` 底下的四個純邏輯模組。

## 7. 雙角色 session（本設計與 App 最根本的差異）

App 的 `SessionProvider` 是掛在根節點的**單例**，一個瀏覽器分頁只有一份登入狀態。左右兩欄要**同時各自登入**，這個形狀行不通。

改為工廠：

```ts
const ElderSession    = createSessionContext("elder");
const GuardianSession = createSessionContext("guardian");
```

每次呼叫產生一組獨立的 Provider 與 hook，持久化 key 分開（`kinsun_web_session_elder` / `kinsun_web_session_guardian`），互不干擾。

持久化用 `localStorage`。`app/` 用的 `expo-secure-store` **在網頁是空實作**（`node_modules/expo-secure-store/src/ExpoSecureStore.web.ts` 內容為 `export default {}`），沒有可搬的路。這是刻意接受的降級：本前端不服務真實長輩，儲存的是內部測試帳號的 token，風險與 admin 金鑰存 localStorage 的既有例外同級（見 `docs/dev/12` §7）。

## 8. 對講機的網頁移植

### 8.1 可原封不動搬過來（純 TypeScript，零 Expo 依賴）

| 模組 | 來源 | 說明 |
| :--- | :--- | :--- |
| `talkGesture.ts` | `app/src/lib/talkGesture.ts` | 按住說話／短按切換的狀態機 |
| `createPlaybackQueue` · `playAndWait` | `app/src/lib/talkSocket.ts` | 播放佇列與「等真的播完」的邏輯 |
| `schedules.ts` | `app/src/lib/schedules.ts` | 排程的人話描述 |
| `notificationsSeen.ts` | `app/src/lib/notificationsSeen.ts` | 已讀水位（儲存改 localStorage） |

**測試一併搬**（`talkSocket.test.ts` 340 行、`talkGesture.test.ts` 75 行、`replyAudioFrame.test.ts` 209 行、`notificationsSeen.test.ts` 55 行）。這些測試刻意不 import 任何 Expo 模組，可直接在 Vitest 下跑。

### 8.2 必須修改的三處（已於 2026-07-30 實測確認）

| # | 問題 | 修正 |
| :-- | :--- | :--- |
| 1 | `talkSocket` 未設 `binaryType`。瀏覽器預設為 `"blob"`，`asArrayBuffer` 收到 Blob 回 `null`，**整個訊框（含字幕）被丟棄**。原始碼註解「本專案不設，故永遠拿到 ArrayBuffer」只在 React Native 成立（見 `app/src/lib/talkSocket.ts:36-54`） | 建立連線後設 `socket.binaryType = "arraybuffer"` |
| 2 | `writeAudio` 注入點原本由 `replyAudio.ts` 提供，該模組依賴 `expo-file-system`，**其網頁實作僅印 warning 後回空值** | 網頁版改回 `URL.createObjectURL(new Blob([bytes], { type: "audio/mp4" }))`，並在播畢後 `revokeObjectURL` |
| 3 | 後端 CSP `media-src 'self' https:` 不含 `blob:`，瀏覽器將拒絕播放上述 blob URL | 後端 CSP 加 `blob:`（見 §10 B3） |

### 8.3 錄音與播放（取代 expo-audio）

- 錄音：`navigator.mediaDevices.getUserMedia({ audio: true })` + `MediaRecorder`
- 手勢事件：`pointerdown` / `pointerup` / `pointercancel`（一套涵蓋滑鼠與觸控）
- 格式：瀏覽器輸出 webm/opus（Safari 為 mp4/aac）。**後端不需修改**——ASR 是寫暫存檔後交給 ffmpeg 解容器（`services/asr/server.py::_decode_to_mono16k`），兩種容器都吃
- 播放：`HTMLAudioElement`，`ended` 事件對應 `didJustFinish`；`playAndWait` 的保險逾時邏輯照搬
- 麥克風權限被拒時顯示白話說明與重試按鈕
- **麥克風必須在 HTTPS 下才可用**。`localhost` 有安全例外，因此本機測試會給出假的安全感——驗收必須在真的 ngrok 網址上做
- ⚠️ **iOS Safari 的音訊解鎖**：iOS Safari 不允許在沒有使用者手勢的情況下播放音訊，而回覆語音是在 WS 訊框抵達時才播——那已經脫離按下麥克風的手勢鏈。標準解法是**在使用者第一次互動時先播一段極短的無聲音訊把播放器解鎖**，之後才播得動。不做這件事的症狀是「iPhone 上只看得到字、聽不到聲音」，而桌機一切正常——這種只在特定裝置出現的症狀最難查

## 9. 兩端連動與模擬通知

`useNotificationFeed(role, token)` 每 **2 秒**輪詢對應端點，比對 `created_at` 水位，有新項目即推入該端手機外框的通知佇列。

| 端 | 端點 | 內容 |
| :-- | :--- | :--- |
| 長輩 | `GET /api/v1/elder-notifications` | 用藥／回診提醒、主動關懷 |
| 家屬 | `GET /api/v1/notifications` | 危急警報、提醒、關懷訊息 |

橫幅從外框頂部滑入、3.5 秒後滑出，可手動關閉。**兩套樣式**（iOS 毛玻璃風、Android Material 風），依 UA 自動選定並提供手動切換——展示時觀眾會想看兩種。

**即時連動**：家屬端完成寫入動作（新增排程、建立長輩）後**立即觸發長輩端重新拉取**，不等下一次輪詢。兩欄在同一個 JS 環境，一個共用的 event bus 即可。

**危急事件路徑後端已現成，不需修改**：長輩講出危急語句 → `pipeline` 判定 → `GuardianNotifier` → `AppOutboundChannel` 寫入 `app_notifications` → 家屬端 2 秒內橫幅滑入。組員自行註冊的帳號沒有 LINE 綁定，`send_text_channels` 找不到 LINE 通道，**真實 LINE 訊息本來就不會送出**，不需額外阻擋。

**排程提醒會真的響**：把提醒設在一分鐘後，等排程器把它寫進 `app_notifications`，橫幅自行跳出。前提是排程器須啟動。

## 10. 後端改動

| # | 改動 | 檔案 | 說明 |
| :-- | :--- | :--- | :--- |
| **B1** | 新增 `GET /api/v1/demo-status` | 新增 `src/kinsun/web/routers/demo_status.py`；`app.py` 掛載 | 公開免認證。分項只回「正常／異常／未知／載入中」，**不回傳版本、主機名、錯誤內容**。ASR／TTS 打各自 `/healthz`（1.5 秒逾時）；資料庫 `SELECT 1`；排程器沿用既有逾期判斷；對話模型看近期呼叫成功率（不空打 Gemini 燒額度）。**結果快取 5 秒**——公開端點不可成為健康檢查的放大器 |
| **B2** | 對講機容量閘門 | `src/kinsun/channels/app/turns.py`、`ws.py` | 見下方細節 |
| **B3** | CSP 兩處放寬 | `src/kinsun/web/security.py` | `media-src` 加 `blob:`（播放 WS 直送的語音）；`script-src` 加 `'wasm-unsafe-eval'`（Chrome 以 `script-src` 管制 WebAssembly 編譯，不加則 `zxing-wasm` 掃碼被自身 CSP 擋死）。`connect-src 'self'` **不必改**——CSP 3 的 `'self'` 涵蓋同源的 `ws:`／`wss:` |
| **B4** | 掛靜態檔 `/demo` | `src/kinsun/app.py` | 比照現有 `/liff`、`/admin` 的 `StaticFiles` 掛載 |

### B2 細節：容量閘門

| 項目 | 內容 |
| :--- | :--- |
| 上限 | 全域同時進行中的對講機輪數，預設 **6**（env 可調，見 §13 待實測） |
| 涵蓋範圍 | `POST /turns` 與 `WS /ws/talk` **共用同一個閘門物件**，否則可從另一條路徑繞過 |
| 與既有機制的關係 | 既有 `_InFlight`（`ws.py:162`）限的是**單一連線**最多 3 輪併發，屬於「同一位長輩連按太多次」；新閘門限的是**全體**同時佔用 GPU 的輪數。兩者並存、目的不同，皆不移除 |
| WS 超限行為 | 送一則 `{"type":"queued","position":N}` 訊框告知排隊位置，前端顯示「金孫正在跟別人說話，前面還有 N 位」；輪到時照常進入處理。**不可靜默丟棄**——長輩不會再講第二次 |
| POST 超限行為 | 請求 hold 住等待，逾時上限 30 秒；逾時回既有的婉拒文案（人話，非裸 429） |
| 帳號級保險絲 | 每個長輩帳號每分鐘 30 輪。純粹防前端 bug（重連迴圈狂送），對真人操作等同無限 |
| 實作位置 | 後端目前單 worker（`kinsun.sh` 的 uvicorn 未指定 `--workers`），進程內計數即可，不需動資料庫。⚠️ 若日後開多 worker，此閘門會退化成「每 worker 各 6 輪」——屆時須改用共享狀態，這一點要寫進程式碼註解 |

**節流的取捨紀錄（W-19）**：原設計含 per-IP 的四個維度。畢業典禮當天廠商與組員共用會場 Wi-Fi＝**同一個對外 IP**，per-IP 節流會讓第二個人開始講話就撞牆，而症狀是「金孫有點累」，看起來像系統壞了。加上網址不對公開網路發布，防陌生人濫用的需求不存在。因此 per-IP 節流、WS 連線數、註冊次數限制**全部移除**；保留的 B2 **不是節流而是容量管理**——ASR 與 TTS 在同一顆 GPU 上，同時湧入的請求不會併行而會排隊，結果是每個人都慢。限制併發並誠實排隊，等於「少數人順暢」勝過「所有人都卡」。既有的登入節流（10 次／300 秒，防猜密碼）目的不同，維持不動。

## 11. 測試策略

| 層級 | 內容 |
| :--- | :--- |
| 單元（Vitest） | 搬移既有 talkSocket／talkGesture／replyAudioFrame／notificationsSeen 測試，另新增 `binaryType` 與 blob URL 兩案；`schedules` 描述；`useDemoStatus` 的三種狀態判定 |
| 元件（testing-library） | 開場頁三狀態的按鈕可點性；通知橫幅進出；**雙 session 互不干擾**（左欄登出不影響右欄） |
| 後端（pytest） | `demo-status` 三種狀態與快取行為；容量閘門的排隊與回報；CSP 標頭含 `blob:` 與 `'wasm-unsafe-eval'` |
| E2E（Playwright） | 完整旅程：註冊家屬 → 建立長輩 → 產生綁定碼 → 長輩端綁定 → 對講機送出一輪 → 家屬端收到通知 |
| 人工 | 麥克風必須在**真的 HTTPS 網址**上驗收（`localhost` 的安全例外會給出假的安全感） |

覆蓋率門檻沿用 `.claude/rules/testing.md` 的 80%。

## 12. 已知風險與相容性約束

| # | 風險 | 處置 |
| :-- | :--- | :--- |
| R-1 | **iOS Safari 音訊解鎖**（見 §8.3）：不處理則 iPhone 上只看得到字、聽不到聲音，桌機一切正常 | 第一次使用者互動時播無聲音訊解鎖；驗收清單必須包含一台真的 iPhone |
| R-2 | **`shared/` 是四端共用的**。`app/` 雖已凍結，改壞 `shared/` 仍會讓它編不過 | `shared/` 原則上**只增不改**；若必須改，同一個 commit 內確認 `app/` 與 `frontend/` 的 typecheck 仍過 |
| R-3 | **MediaRecorder 的容器格式各家不同**（Chrome/Firefox 給 webm/opus，Safari 給 mp4/aac） | 後端 ffmpeg 兩者皆吃，不需處理；但**驗收必須跨三家瀏覽器實測**，不可只在 Chrome 上測完就宣稱可用 |
| R-4 | **展示當天無程式層備案**（W-22 決定不做離線模式）。DGX、ngrok、會場網路任一出狀況即開天窗 | 設計上接受。建議彩排時自行錄一段螢幕錄影當最低限度的保險——這不在本設計的施工範圍內 |
| R-5 | **`/demo` 與後端同生共死**：後端關閉時網址整個連不上，運營狀態頁顯示不出來 | W-21 已接受。運營狀態頁的實際用途是「後端活著但某個服務沒開」，這一點仍然成立 |
| R-6 | **WS 的 token 走 query string**（協定限制，瀏覽器與 RN 皆無法自訂握手標頭），會進入反向代理的存取日誌 | 既有行為，`app/` 亦然；本前端只有內部測試帳號，風險接受。已見 `ws.py` 既有註解 |

## 13. 待實測後才能定的數字

以下數字目前**沒有實測依據**，先給預設值並做成可調，須於彩排時量測後定案：

| 項目 | 暫定值 | 量測方式 |
| :--- | :--- | :--- |
| 全域同時併發輪數上限 | 6 | 讓 N 人同時講話，觀察往返延遲何時開始難看 |
| 通知輪詢間隔 | 2 秒 | 觀察展示時「連動」的體感是否夠即時 |
| ASR／TTS healthz 逾時 | 1.5 秒 | 觀察狀態頁載入是否被拖慢 |

## 14. 文件同步（AGENTS.md 鐵律）

| 文件 | 需更新內容 |
| :--- | :--- |
| `docs/dev/05_架構與設計.md` | 前端由三端變四端；`web/` 的定位 |
| `docs/dev/06_API設計規範.md` | 新增 `GET /api/v1/demo-status` |
| `docs/dev/07_模組規格與測試.md` | `web/` 模組與測試清單 |
| `docs/dev/08_專案結構指南.md` | 新增 `web/` 目錄 |
| `docs/dev/09_模組依賴關係.md` | `web/` → `shared/` 依賴 |
| `docs/dev/12_前端架構規範.md` | 四端分工；`app/`／LIFF 凍結；雙 session 工廠；對講機的網頁移植三處修正 |
| `docs/dev/17_前端資訊架構.md` | `web/` 的頁面職責與路由 |
| `docs/dev/README.md` | 文件狀態表 |
| `.env.example` | 容量閘門相關鍵，附預設值與一行中文註解 |
| `scripts/kinsun.sh` | `web` 的 build 與 dev server |

## 15. 明確不做

離線示範模式（W-22）· Web Push（W-14）· 深色模式（W-10）· admin 後台（W-05）· landing page（W-12，以後另做）· 示範帳號一鍵登入（W-20，組員代操）· 結業後的獨立告示頁（W-21）· 修改 `app/` 與 `frontend/`（W-07）
