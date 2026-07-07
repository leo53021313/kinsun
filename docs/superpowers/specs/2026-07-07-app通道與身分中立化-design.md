# 雙平台 App 與身分層通道中立化 — 設計文件

- 日期：2026-07-07
- 狀態：已與需求方確認方向，待實作計畫
- 相關文件：
  - `CONTEXT.md`（領域語彙：通道／入站訊息／出站通道）
  - `docs/mvp/07_Tech_Design.md`（§8 橫切面 seams 表）
  - `docs/superpowers/plans/2026-06-29-入站事件正規化.md`（通道抽象的原始設計）
  - `docs/superpowers/specs/2026-07-03-naming-decisions.md`（`elder_id` 與 `line_user_id` 不合併的命名決策）
  - `docs/全庫人工決策盤點-待議.md`（本設計順帶解決其中三項風險）

---

## 1. 背景與動機

目前系統唯一的使用者通道是 LINE，實務上遇到五個痛點：

1. **UI/UX 無法自訂**：只能靠訊息泡泡、圖文選單與 LIFF 網頁，做不出大字體長輩介面與即時對話畫面。
2. **語音體驗不順**：長輩要手動按錄音、手動點播放，無法自動播放回覆；主動關懷只能發文字。
3. **推播與平台限制**：推播訊息有額度與費用，訊息格式受 LINE 規格牽制。
4. **帳號綁定脆弱**：身分綁在 `line_user_id` 上，長輩換手機記憶就變孤兒，且無重綁流程。
5. **測試困難**：長輩與家屬是兩個 LINE 身分，測綁定流程需要兩支手機兩個帳號，無法自由切換。

因此決定開發 iOS + Android 雙平台 App（長輩端＋家屬端），並把後端身分層改造成通道中立。

## 2. 需求彙整（已確認）

| 面向 | 決定 |
|---|---|
| 目標使用者 | 長輩端＋家屬端都要 |
| 語音互動 | 對講機模式（按著說話→放開送出→自動播放回覆）；之後加虛擬形象（前端表現層，預留元件位置） |
| LINE 去留 | 現階段不決定 → 架構做成通道中立，去留都不需改程式 |
| 登入方式 | 家屬：email＋密碼；長輩：家屬產生綁定碼，輸入一次後裝置永久登入 |
| 配對關係 | 一位長輩可配對多位家屬、一位家屬可配對多位長輩（多對多） |
| 發布方式 | 不上架，開發版於實體 iPhone / Android 測試機預覽 |
| 團隊現況 | 無行動開發經驗，以 AI 協助開發；無 Mac、無付費 Apple 開發者帳號 |
| 時程 | 無硬期限，正確性優先於速度 |
| 施工策略 | B：地基優先，一路往上（先身分層、再通道、再 App） |

## 3. 技術選型：React Native + Expo（TypeScript）

**決定性理由——沒有 Mac：**Expo Go 是唯一不需要 Mac 就能在實體 iPhone 上預覽的路徑（iPhone 安裝免費的 Expo Go，掃 QR code 直接執行開發中的 App）。Flutter 的 iOS 建置必須依賴 Xcode（＝必須有 Mac 或付費雲端代建），原生 SwiftUI 則連開發都離不開 Xcode，兩者皆不可行。

其他理由：

- **語言與知識延續**：現有前端（`frontend/`）即為 React 18 + TypeScript，API 呼叫模式、snake_case 欄位型別定義可直接沿用思維。
- **AI 開發相容性**：團隊以 AI 協助開發，React Native + Expo 生態的 AI 產出品質與除錯可靠度最高。
- **功能套件現成**：錄音／播放（expo-audio）、推播（expo-notifications）、動畫形象（Rive／Lottie 皆有 RN 支援）。

**已評估並排除的替代方案：**

| 方案 | 排除原因 |
|---|---|
| Flutter | iOS 建置必須 Mac／付費雲端 CI；Dart 為全新語言，既有 React 知識零重用 |
| 原生雙寫（SwiftUI＋Kotlin） | 兩套程式碼兩倍維護量；無 Mac 時 iOS 端完全無法開發 |
| PWA（網頁 App） | iOS 對網頁錄音、推播、鎖屏喚醒支援殘缺；長輩心智模型偏好桌面圖示開啟原生 App |

**取捨（誠實面）**：若未來需要深度原生客製（如即時語音串流的低延遲音訊處理），可能需要撰寫原生模組並回頭依賴 Mac；但 MVP 範圍（表單管理＋錄音上傳＋播放回覆）遠未及此天花板。

## 4. 架構設計

### 4.1 身分層通道中立化（地基）

**核心原則：記憶跟「人」走，不跟「通道」走。**

現況全系統以 `line_user_id` 為會話主鍵（全 src 出現約 499 次），記憶、危急事件、對話摘要皆掛在 LINE 帳號上，此為換手機記憶孤兒問題的根因。重構內容：

1. **新增 `channel_bindings` 表**：

   ```sql
   CREATE TABLE channel_bindings (
     channel        TEXT NOT NULL,          -- 'line' | 'app'
     external_id    TEXT NOT NULL,          -- LINE userId 或 App 裝置帳號 ID
     principal_type TEXT NOT NULL,          -- 'elder' | 'guardian'
     principal_id   TEXT NOT NULL,          -- elder_id 或 guardian_id
     created_at     DOUBLE PRECISION NOT NULL,
     PRIMARY KEY (channel, external_id)
   );
   ```

   一個人可同時擁有 LINE 綁定與 App 綁定；換手機＝更新一筆綁定，記憶不動。`elders.line_user_id`、`guardians.line_user_id` 欄位資料遷入本表後退役。

2. **會話主鍵改為 `elder_id`**：`turns`、`conversation_summaries`、`risk_events`、Mem0 長期記憶的鍵由 `line_user_id` 遷移為 `elder_id`；Agent、Pipeline、記憶模組（shortterm／longterm／recall）方法簽名同步更改。既有資料以 `elders.line_user_id` 映射回填，不遺失。

3. **通道識別只活在邊界**：
   - 入站：`InboundMessage` 攜帶 `(channel, external_id)`，`dispatch` 入口先解析為本人（elder／guardian），之後管線只認 `elder_id`。綁定前的對話（binding_sessions 流程）仍以通道身分運作。
   - 出站：`OutboundChannel` 收件人由 `line_user_id` 改為通道中立的本人識別；發送前查 `channel_bindings` 決定投遞通道。未來危急通知可多通道並發。

4. **順帶解決待議清單三項已知風險**：換手機記憶孤兒（`docs/全庫人工決策盤點-待議.md`）、`elders.line_user_id` 無 UNIQUE 約束、`risk_events` 缺 `elder_id`。

5. **觀測五表**（`webhook_events`／`asr_calls`／`llm_calls`／`tts_calls`／`replies`）屬事件日誌，維持記錄通道層識別即可；補記 `elder_id` 欄位**延後**至管理端出現以人查詢的需求時一併做（1C 實作時評估：改動面涵蓋五表 DDL 與 TraceStore 全簽名，現階段無讀取端受益，YAGNI）。不做歷史回填（日誌性質，成本效益不符）。

### 4.2 App 帳號與認證

- **家屬**：email＋密碼註冊登入。密碼以標準雜湊演算法儲存（優先使用 Python 標準庫 `hashlib.scrypt`，避免新增依賴套件）；登入後發放 API token（雜湊後存 DB 的不透明 token，可撤銷，不引入 JWT 依賴）。
- **長輩**：不碰帳密。家屬在 App 中替長輩產生**綁定碼**（沿用既有 `invites` 表與綁定碼概念），長輩手機輸入一次後，該裝置取得長期 token 永久登入，同時寫入一筆 `channel_bindings(channel='app', ...)`。
- **多對多配對**：既有 `elder_guardians` 關聯表（複合主鍵 `(elder_id, guardian_id)`，含 `role`、`escalation_order`、`can_view_transcript`）已支援多對多；App 的家屬邀請流程沿用既有邀請碼機制。
- 新增環境變數依規範掛子系統前綴（`APP_` 為 App 通道子系統），全數列入 `.env.example`。
- 測試效益：測試帳號可自由建立，不再需要兩個 LINE 帳號。

### 4.3 App 通道後端（`channels/app/`）

與 `channels/line/` 平行的第二通道，重用既有接縫：

- **對講機語音 API**：`POST /api/app/turns`——App 上傳錄音檔（multipart），後端走既有 ASR→LLM→TTS 管線，同一個 HTTP 回應回傳回覆文字＋回覆音檔 URL。命名沿用領域語彙「turn（對話回合）」與「複數名詞」路徑規範。同步請求／回應模式，比 LINE 的 webhook／reply 更簡單。
- **入站**：App 請求轉為 `InboundMessage` 進既有 `dispatch`；`reply`／`reply_voice` callable 改為「收集回覆內容供 HTTP 回應返回」的實作。
- **出站**：實作 `AppOutboundChannel`（`OutboundChannel` Protocol）；開發期主動訊息暫存為 App 可拉取的收件匣，推播接上後改推送。
- **家屬端 REST API 直接重用**：既有 `/api/me/elders`、用藥、回診、健康報告等端點內部本來就使用 `elder_id`／`guardian_id`，僅需把認證層由「LIFF idToken 驗證」換成「App token 驗證」（兩者並存，LIFF 不拆）。

### 4.4 Expo App（`app/` 單一專案）

- **一個專案、一個 App、兩種角色**：登入方式決定介面——家屬帳密登入進管理介面（長輩列表、用藥、回診、健康報告）；長輩綁定碼登入進對講機介面（整頁大按鈕：按著說話、放開送出、自動播放回覆）。
- **目錄結構**：`app/` 為單一 Expo 專案（TypeScript）；`app/ios`、`app/android` 為 Expo prebuild 自動生成的平台目錄，非兩套程式碼。
- **開發流程**：開發機執行 `npx expo start`，測試機以 Expo Go 掃 QR code 即時預覽與熱更新；後端 endpoint 以 `EXPO_PUBLIC_API_URL` 環境變數設定（沿用位置無關原則）。
- **虛擬形象預留**：對講機介面中央預留「形象區」元件（MVP 先放靜態插圖＋說話狀態動畫），日後替換為 Rive／Live2D 動態形象時不改架構。

### 4.5 推播通知（延後階段，需要時啟動）

- 提醒與危急通知推送至 App 需 FCM／APNs → 需付費 Apple Developer 帳號（美金 99／年）＋ EAS 雲端建置（dev build），屆時仍不需要 Mac。
- 過渡期策略：危急通知繼續走 LINE 綁定（若存在）；App 在前景時以輪詢或 WebSocket 接收。

## 5. 施工階段（策略 B：地基優先）

| 階段 | 內容 | 性質 |
|---|---|---|
| 1 | 身分層通道中立化（`channel_bindings`、會話主鍵遷移、邊界解析） | 純後端重構＋資料遷移 |
| 2 | App 帳號與認證（家屬帳密、長輩綁定碼、token） | 後端新功能 |
| 3 | App 通道後端（`channels/app/`、`POST /api/app/turns`、家屬 API 換認證） | 後端新功能 |
| 4 | Expo App（`app/` 專案、雙角色介面、Expo Go 實機預覽） | 前端新專案 |
| 5 | 推播通知（購買 Apple 帳號、EAS build、FCM/APNs） | 需要時啟動 |

## 6. LINE 模組處置

**不刪、降級、凍結。**

- `channels/line/` 原封保留，繼續服務現有使用者。
- 身分解析職責移出（LINE 不再壟斷身分，`line_user_id` 成為 `channel_bindings` 中 `channel='line'` 的一種綁定）。
- 凍結新功能開發。
- App 穩定並觀察長輩端實際採用率後，再決定退場或長期並存——通道中立架構下兩條路皆不需改程式。

## 7. 測試策略

- 新增 store 遵循三件套（Protocol＋Pg＋Fake）與合約測試（`test_<領域>_store_contract.py`）。
- `channels/app/` 比照 `channels/line/` 的測試方式：餵 `InboundMessage` 斷言行為，不依賴真實 HTTP。
- 身分層遷移撰寫遷移前後對照測試（`KINSUN_IT=1` 整合測試驗證 Postgres 遷移腳本）。
- App 端以 Expo Go 於實體 iPhone／Android 測試機人工驗證。

## 8. 主要風險與取捨

| 風險 | 對策 |
|---|---|
| 階段 1 改動面大（`line_user_id` 約 499 處） | 合約測試＋既有測試套件護航；分小步提交；先立 seam 再遷移 |
| 階段 1–2 無畫面產出 | 需求方已知悉並接受（地基優先為明確選擇） |
| Expo Go 限制：開發期無推播 | 推播列為階段 5；過渡期以 LINE／前景輪詢替代 |
| 長輩端 App 採用門檻 | LINE 通道不退場，雙軌並行觀察採用率 |
| Mem0 長期記憶鍵遷移 | 遷移腳本需涵蓋 Mem0 的使用者鍵；於實作計畫中列為獨立工項 |

## 9. 未決事項

- LINE 通道最終去留（觀察 App 採用率後決定）。
- 虛擬形象技術選型（Rive／Live2D／Lottie，屆時另開設計）。
- 即時語音串流演進（串流 ASR/TTS＋WebSocket，屆時另開設計）。
- 推播啟動時機（購買 Apple Developer 帳號的時間點）。
