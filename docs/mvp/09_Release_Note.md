# 09 Release Note — 金孫 KinSun

> **文件性質**：依 git 歷史與 [progress.md](../../progress.md) 反向整理的版本說明。
> 本專案尚未正式發版，此為 **MVP 現況快照（截至 2026-07-06，Leo 分支）**；
> 首次對外發布前請依本檔格式補齊正式版號。
> ⚠️ 標記者為未拍板事項，對應 [全庫人工決策盤點-待議](../全庫人工決策盤點-待議.md)。

---

## v0.9-mvp（未發布快照，2026-07-06）

**開發區間**：2026-06-26（Initial commit）～ 2026-07-06，約 394 筆提交。
**狀態**：功能面「看似完成」，但 52 項團隊決策（24 項 P0）＋18 項工程確認未拍板；
**尚未經過**真 LINE 帳號完整實測（[功能實測驗收清單](../功能實測驗收清單.md) A–E 區皆 ⬜ 未測）。

### 新功能（Features）

**長輩端對話**
- LINE 語音／文字對話主流程：webhook → ASR → 危急偵測 → CareAgent（Gemini）→ TTS 語音回覆
- 金孫人設（孫輩口吻、安全邊界）⚠️ T-35：prompt 未經人核定
- 短期記憶（今日對話）＋長期記憶（Mem0＋pgvector）＋用藥事實每輪注入
- 天氣工具（function calling）⚠️ T-52：geocoding 取全球第一筆

**安全守護**
- 危急偵測 L0–L3：關鍵詞絕對覆蓋＋Gemini 分級，fail-safe 設計 ⚠️ T-02／T-04／T-05
- L2 以上即時推播全體已綁定家屬（LineGuardianNotifier）⚠️ T-03／T-06～T-08
- 危急事件持久化（`risk_events`，掛 trace_id）

**帳號與同意**
- 引導式綁定（「設定」→ 建立長輩／邀請家屬／貼碼綁定），狀態存 `binding_sessions`
- 知情同意於確認步驟顯示，`consent_by=SELF` ⚠️ T-19：CONSENT_VERSION 指向不存在的條款
- 綁定閘門（`BINDING_GATE_ENABLED`，預設關閉）

**排程與主動關懷**
- 排程 worker：用藥提醒（早／中／晚／睡前）、回診提醒、早安問候、失聯關心、
  夜間記憶整理、對話摘要、音檔清理、觀測資料清理 ⚠️ T-30～T-33
- 提醒紀錄持久化（`reminder_logs`）

**家屬端**
- LIFF 儀表板（React＋Vite＋TS）：長輩清單、用藥 CRUD、回診 CRUD、健康報告、邀請碼 ⚠️ T-43：零樣式
- 家屬圖文選單（Rich Menu）自動授予 ⚠️ E-07：佈建腳本疑似從未成功跑過
- 家屬 REST API（LIFF idToken 驗證）

**真模型（DGX）**
- ASR 服務：Breeze-ASR-26，GPU＋fp16 實機驗證通過（~1.1 秒／句）
- TTS 服務：CosyVoice 3 國語，實機驗證通過（RTF≈0.7），m4a 上傳 Supabase Storage
  ⚠️ T-39：聲音為範例聲、授權未處理 ⚠️ T-41：真 LINE 播放未驗證

**觀測後台**
- 觀測五表（webhook_events／asr_calls／llm_calls／tts_calls／replies）貫穿 trace_id
- `/admin` 唯讀後台：總覽、訊息流、長輩時間軸、單輪鏈路（X-Admin-Key 驗證）

**工程基礎**
- 三件套持久層（Protocol＋Pg＋Fake）×11 領域、store 合約測試全掃齊
- 統一傳輸層 `Transport`、出站通道門面 `OutboundChannel`、共用組裝核心 `Core`
- 全功能啟停腳本 `scripts/kinsun.sh`

### 已知問題（Known Issues）——首次發布前必須處理的 P0 摘錄

| 編號 | 問題 |
|------|------|
| T-01 | 打字求救完全繞過危急偵測 |
| T-05 | LLM 故障時語意偵測靜默歸零，無人會知道 |
| T-11 | 警報推播全數失敗也只記一行 log（送出≠送達） |
| T-12 | 長輩失聯 30 天＝連發 28 則關心，家屬毫不知情 |
| T-14／T-15 | 逐字稿永久保存、撤回同意無入口 |
| T-25 | 解除綁定／移除家屬／換手機重綁全部不存在 |
| T-30 | 主動關懷不經同意閘門 |
| T-32 | 用藥提醒單次推播、無確認、失敗當天靜默放棄 |
| T-42 | webhook 同步跑完整管線（最壞 >115 秒）vs reply token 短效 |
| T-48／T-49 | 最便宜 LLM 檔位統包全部任務；DGX 服務無認證 |

完整清單（52＋18＋約 45 條）見 [全庫人工決策盤點-待議](../全庫人工決策盤點-待議.md)。

### 升級／部署注意（Breaking / Ops Notes）

- 記憶層已上雲：啟動 webhook／scheduler **必須**雲端金鑰（`DATABASE_URL`、`GEMINI_API_KEY`、LINE），本機已無 SQLite。
- Supabase 需啟用 pgvector，並手動建立公開 Storage bucket（預設 `tts-audio`）。
- 家屬 LIFF 需先建 LINE Login channel＋LIFF app（`LIFF_CHANNEL_ID`／`VITE_LIFF_ID`），
  未設定時整個家屬端 401 ⚠️ E-12。
- 前端需 `npm run build`＋`npm run build:admin` 產出 dist，後端才會供應 `/liff` 與 `/admin`。
- 測試綠燈 ≠ 真整合可行：`uv run pytest` 全離線 fake，真整合請走 [功能實測驗收清單](../功能實測驗收清單.md)。

---

## 發布流程建議（下一版起）

1. 版號規則：`v<主>.<次>-<階段>`（如 `v1.0-pilot`），git tag 對應。
2. 每版 Release Note 固定四節：新功能／修正／已知問題／升級注意。
3. 發布前閘門：實測清單 A–E 全 ✅＋P0 待議項清零（或明文接受風險）。
