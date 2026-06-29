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
與長輩往來訊息的傳輸面。目前只有 LINE，藍圖含 web／app／電話語音。
_Avoid_: 平台、介面、端點

**入站訊息（InboundMessage）**：
通道轉接器把原始事件正規化後、與通道無關的領域型別：`session_id`、種類（文字／語音）、文字內容、語音 bytes，以及一個可呼叫的回覆 handle。分派邏輯只認這個型別，不碰 LINE SDK。
_Avoid_: event、payload

**會話（Session）**：
一位長輩的對話脈絡，以 LINE user_id 識別（即 `session_id`）。

### 記憶與情境

**短期記憶（Short-term memory）**：
今日對話的逐輪記錄（`turns` 表），作為訊息歷史餵入 LLM。
_Avoid_: 歷史、快取

**長期記憶（Long-term memory）**：
經夜間整理萃取、跨日保留的長者事實（Mem0／pgvector）；檢索時每輪固定附帶穩定健康事實。
_Avoid_: 知識庫、向量庫

**注入情境（Injected Context）**：
每輪附加到 system prompt 的長者事實集合（長期記憶 ＋ 用藥事實 ＋ 未來其他事實），由 `MemoryContext` 組裝。
_Avoid_: prompt、記憶字串

**用藥事實（MedicationFacts）**：
長輩當前用藥清單，作為注入情境的一部分每輪固定帶；由 LINE 帳號解析到 elder 後查得。
_Avoid_: 藥單、處方

### 安全與關懷

**危急分級（RiskTier／RiskAssessment）**：
L0–L3 四級危急程度與其評估結果；融合關鍵詞與 LLM 分級，後端複核。
_Avoid_: 警報等級、嚴重度

**主動關懷（Proactive care）**：
由排程觸發、agent 主動開啟的對話（早安問候、失聯關心、用藥提醒）。
_Avoid_: 推播、通知
