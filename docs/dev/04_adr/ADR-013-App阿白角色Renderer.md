# ADR-013：Expo App 以離線 WebView 納入阿白角色 renderer

> **狀態:** 已接受 | **日期:** 2026-08-07 | **決策者:** 專案負責人（「納入並連接」）

## 1. 背景與問題

新視覺交接指定阿白為長輩端角色，並提供 Otto `pet-core` 的 SVG、動作、情緒與注音 viseme。正式 App 已有錄音、WebSocket／POST 降級、分段 TTS、Risk Engine 與 LLM 管線；若直接啟動 Otto 完整應用，會再建立一套麥克風、LLM、TTS、定位與外部網路流程，破壞現有安全與延遲契約。

## 2. 考量的選項

- **A．完整 Otto 頁面放進 WebView**：接入快，但會重複麥克風／對話／外部服務與憑證，且正式後端不再是唯一安全來源。
- **B．只納入 renderer，以版本化 bridge 連接正式 App**：保留 SVG／動作／viseme，App 只送既有五態、當段文字與 `duration_ms`；需維護產生式 HTML 與 WebView 邊界。
- **C．把 Otto 全部重寫成 React Native／react-native-svg**：原生整合最深，但改寫面大，容易在六批視覺交接期間引入角色骨架與對嘴回歸。
- **D．維持靜態圖**：風險最低，但無法使用已交付的可對嘴向量角色，也不符合「納入並連接」決定。

## 3. 決策

採 **B：renderer-only 離線 WebView adapter**。

- `OttoBearRenderer` 載入由白名單腳本產生的單一 HTML asset。
- `ottoBridge` 使用 `version=1`、單調 `sequence` 與既有 `TalkVisualState`；speaking 才可帶文字、時長與選填情緒。
- `talk.tsx` 在每段音訊真正開始播放時送 cue，第一段不等待整段合成；`talkGesture.ts`、`talkSocket.ts`、`talkPresentation.ts` 不修改。
- 正式 `agent.py`、Risk Engine、ASR／TTS 與播放佇列維持唯一行為來源。Otto `brain.js` 只作上游人設參考，不進 runtime。
- renderer CSP 為 `default-src 'none'`；不納入 Otto 的麥克風、LLM、TTS、定位、天氣、食物、場景與互動網路模組。
- 原生 WebView 未 ready／失敗時顯示靜態暫用圖；Expo Web 因套件不支援瀏覽器，也固定降級為靜態圖。

## 4. 後果

- **正面**：保住正式對講、安全與第一段低延遲契約；可直接使用 Otto 向量與 viseme；角色呈現失敗不阻擋長輩說話。
- **代價**：增加 `react-native-webview`、約 3MB 的離線 HTML asset、vendor 白名單與 build/check 腳本；需要 Android／iOS 真機驗收透明背景、效能與 reduced motion。
- **限制**：批次 1 只完成 renderer 接縫；209×300 固定舞台、top 140、回話卡與 132→72 主鍵變形仍由批次 3 施工。正式五張系統態 PNG 與 speaking 素材未交付時，靜態降級仍使用暫用圖。
- **重新評估觸發**：WebView 在目標低階裝置上無法維持流暢，或正式角色素材改為可直接由 React Native renderer 消費的格式時，再評估選項 C。
