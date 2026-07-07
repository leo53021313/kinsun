# 金孫（kinsun）

聽懂國台語的長輩 AI 語音陪伴守護 Agent：透過 LINE 與長輩語音對話，記住長者事實、偵測危急並通知家屬。本檔為本專案的領域語彙唯一來源，命名與溝通請採用以下用語。

## Language

### 角色與帳號

**長輩（Elder）**：
被陪伴與守護的對象；以 `elder_id` 為主鍵，可綁定一個 LINE 帳號。
_Avoid_: 用戶、病人、老人

**家屬（Guardian）**：
長輩的家人；接收危急通知、可被邀請加入並依升級順序被聯絡。
_Avoid_: 監護人、聯絡人

**綁定（Binding）**：
把一個 LINE 帳號與「長輩本人」或「家屬」身分建立關聯的引導式對話流程。
_Avoid_: 註冊、登入

**邀請碼（Invite）**：
一次性代碼，家屬產生、對方在聊天視窗貼上以完成綁定；有時效與嘗試次數上限。
_Avoid_: token、優惠碼

**同意（Consent）**：
長輩本人對「記錄對話並在必要時通知家人」的知情同意；是綁定閘門（放行語音對話）的依據。
_Avoid_: 授權、許可

### 通道與訊息

**通道（Channel）**：
與長輩往來訊息的傳輸面。目前只有 LINE，藍圖含 web／app／電話語音。兩個方向皆通道中立：入站是 `InboundMessage` 型別，出站是 `OutboundChannel` 門面。
_Avoid_: 平台、介面、端點

**入站訊息（InboundMessage）**：
通道轉接器把原始事件正規化後、與通道無關的領域型別：`channel`＋`external_id`（來源通道與其帳號識別）、種類（文字／語音）、文字內容、語音 bytes，以及一個可呼叫的回覆 handle。分派時由閘門把 (channel, external_id) 解析成本人，之後管線只認 `elder_id`；分派邏輯不碰 LINE SDK。
_Avoid_: event、payload

**出站通道（OutboundChannel）**：
對單一通道帳號送訊息的門面（`channels/outbound.py`）：`send_text(external_id, text)`。LINE 版 `LineOutboundChannel` 為 adapter（內部呼叫 `push_message`）。主動關懷、提醒 jobs、危急通知不直接呼叫它，改依賴通道路由（ChannelRouter）；未來語音再於此加 `send_voice`。
_Avoid_: Pusher、push_text、messenger

**通道路由（ChannelRouter）**：
本人 → 綁定通道的出站路由（`channels/router.py`）：`send_text(principal_type, principal_id, text)` 查 `channel_bindings` 後對每個已綁定且有 adapter 的通道各送一次，單通道失敗隔離。新增通道＝多註冊一個 adapter，呼叫端不變。
_Avoid_: dispatcher、broadcaster

**通道綁定（ChannelBinding）**：
通道帳號對應本人的持久對應（`channel_bindings` 表）：`(channel, external_id) → (principal_type, principal_id)`。一人可同時有 LINE 與 App 綁定；換手機＝改一筆綁定，記憶不動。擴張—收縮遷移已全程完成（1A–1D）：會話主鍵、帳號讀取端、入站解析、出站路由皆以本表為準，`elders.line_user_id`／`guardians.line_user_id` 欄位已退役、綁定由帳號服務直接寫入。
_Avoid_: mapping、link、account_binding

**App 帳號（GuardianAccount）**：
家屬的 App 登入身分（email＋scrypt 密碼雜湊，`guardian_accounts` 表）；與 LINE 綁定並存，同一位家屬可同時有兩種入口。長輩不設帳密——以家屬產生的綁定碼換**裝置 token** 永久登入。
_Avoid_: user、account（泛稱）

**API token（ApiToken）**：
App 呼叫 REST 的不透明憑證：發放時回明文一次，DB 僅存 SHA-256（`api_tokens` 表），撤銷＝刪列。以 `principal_type`＋`principal_id` 指向本人，家屬與長輩共用同一機制。
_Avoid_: JWT、session id

**會話（Session）**：
一位長輩的對話脈絡，以 `elder_id` 識別（通道中立，記憶跟人走）；通道識別（如 `line_user_id`）只活在邊界，於入站閘門解析成本人。

### 記憶與情境

**短期記憶（Short-term memory）**：
今日對話的逐輪記錄（`turns` 表），作為訊息歷史餵入 LLM。
_Avoid_: 歷史、快取

**長期記憶（Long-term memory）**：
經夜間整理萃取、跨日保留的長者事實（Mem0／pgvector）；檢索時每輪固定附帶穩定健康事實。
_Avoid_: 知識庫、向量庫

**注入情境（Injected Context）**：
每輪附加到 system prompt 的長者事實集合（長期記憶 ＋ 用藥事實 ＋ 未來其他事實）。為結構化型別 `InjectedContext`（`MemoryItem` 清單 ＋ 各 `FactSection`），由 `SessionMemory` 組裝、`format_injected_context` 統一排版成 prompt 字串。
_Avoid_: prompt、記憶字串

**會話記憶（SessionMemory）**：
`CareAgent` 對「本次會話短期記憶 ＋ 情境」的單一門面（`memory/recall.py`）：`assemble(elder_id, query) -> TurnContext` 一手包三層（今日對話 ＋ 長期記憶 ＋ 事實），`record_turn(elder_id, *messages)` 記錄本輪。agent 不再直接碰 `MemoryStore`。
_Avoid_: MemoryContext、context

**單輪情境（TurnContext）**：
`SessionMemory.assemble` 的回傳：`injected`（結構化注入情境，供測試斷言）＋ `history`（今日對話訊息串）＋ `system_suffix`（`injected` 排版後的 prompt 後綴，供 agent 貼上）。
_Avoid_: prompt、bundle

**用藥事實（MedicationFacts）**：
長輩當前用藥清單，作為注入情境的一部分每輪固定帶；以 `elder_id` 直查。
_Avoid_: 藥單、處方

### 安全與關懷

**危急分級（RiskTier／RiskAssessment）**：
L0–L3 四級危急程度與其評估結果；融合關鍵詞與 LLM 分級，後端複核。
_Avoid_: 警報等級、嚴重度

**主動關懷（Proactive care）**：
由排程觸發、agent 主動開啟的對話（早安問候、失聯關心、用藥提醒）。
_Avoid_: 推播、通知

**健康報告（HealthReport）**：
家屬端看的長輩近況彙整：近 N 天（預設 30）的危急事件 ＋ 提醒紀錄。由 `reports/health.py` 的 `build_health_report` 組裝（以 `elder_id` 直查、依時間窗過濾），route handler 只驗身分並出 JSON。與 observability 的管理端活動時間軸（feed／timeline）是不同報告、不同受眾。
_Avoid_: 儀表板、timeline、feed

**組裝根（Composition Root）**：
把設定與各元件接成可服務程式的入口；本專案有兩個——`build_app`（FastAPI 網站）與 `build_scheduler`（排程 worker）。兩者共用的物件圖只在一處組裝，各自只補自己專屬（edge-specific）的接線。
_Avoid_: 進入點、main

**外部相依（Externals）**：
會連線或需真實金鑰的重量級 adapter：資料庫連線、Gemini、Mem0 長期記憶、LINE 傳訊。由 `build_externals(settings)` 建一次；因為建構當下即連網，不進單元測試。
_Avoid_: client、資源

**組裝核心（Core）**：
兩個組裝根共用的物件圖：帳號、短期記憶、注入情境、裝滿工具的 CareAgent、traces、reminder_logs 等。由 `assemble_core(settings, externals, *, clock)` 純接線組出——不連網、可離線用假 Externals 測——回傳 frozen dataclass。root-specific 的 pipeline／jobs 不屬於 Core。
_Avoid_: 容器、context、god object

### 測試（Testing）

**合約測試（Store contract）**：
一份行為斷言，同時參數化跑一個 seam 的兩個 adapter——`Fake<領域>Store`（離線、每次都跑）與 `Pg<領域>Store`（連真庫、`KINSUN_IT=1` 才跑）——用以證明兩個 adapter 對同一情境給出相同結果。檔名 `test_<領域>_store_contract.py`。
_Avoid_: 整合測試（僅指 Pg 那半）、單元測試

### 傳輸（Transport）

**傳輸（Transport）**：
app 層對外 HTTP 的統一出口（`src/kinsun/transport.py`）：`Transport` Protocol 只有一個 `request(method, url, *, data, headers, timeout) -> Response`，正式用 `UrllibTransport`，錯誤統一為 `TransportError`。各 client（asr／tts／audio／auth／weather）建構時可注入，預設 `UrllibTransport`；測試注入假版，不再 monkeypatch urllib 全域。
_Avoid_: HttpClient、requests、連線
