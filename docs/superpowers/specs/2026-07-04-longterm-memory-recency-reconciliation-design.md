# 長期記憶讀取時的「新覆舊」矛盾消解 — 設計文件

- 日期：2026-07-04
- 狀態：已與需求方（Leo）確認，待實作
- 影響範圍：`src/kinsun/memory/longterm/store.py`（單一檔）＋其單元測試

## 1. 背景與問題

長期記憶子系統以 Mem0（`mem0 2.0.10`）為後端，向量庫在 Supabase（`vecs.kinsun_memories`）。夜間整併批次 `daily-consolidation` 每天把「前一天」的短期對話餵入 Mem0。

實測發現：當長輩更正既有偏好時，長期記憶會**同時保留互斥的兩筆事實**。例如某測試帳號的長期記憶：

- （舊，07-03）使用者喜歡吃日式料理，特別是壽司與生魚片。
- （新，07-04 更正後）使用者表示不喜歡吃壽司與生魚片，並明確指出喜歡吃麥當勞。

兩筆並存，檢索（語意 top-k）時可能一起被撈出餵給 agent，機器人有機率回退到舊的「壽司」。

### 根因（已於程式碼層驗證）

`mem0 2.0.10` 的 `add()` 走 **additive extraction（純新增）** 架構：

- `_add_to_vector_store` 的 Phase 6 **硬寫 `"event": "ADD"`**，架構上不會產生 UPDATE / DELETE。
- 唯一「調和」是：完全相同文字的 hash 去重、以及 `linked_memory_ids` 軟連結（不覆蓋）。
- 舊版 `DEFAULT_UPDATE_MEMORY_PROMPT`（兩階段 UPDATE/DELETE 決策）在 2.0.10 為死碼，未被呼叫；`MemoryConfig` 也無 `custom_update_memory_prompt` 欄位可注入。
- config 的 `"version": "v1.1"` 只決定回傳格式（`{"results": [...]}`），不改變寫入分流。

**結論**：矛盾消解在此 mem0 版本無法靠 prompt 於寫入端達成，只能做在應用層。Mem0 官方在 2.x 刻意把「該信哪個」的決定權下放到檢索/使用端，這與本專案抽取 prompt 第 3 條「對認知退化者的矛盾不爭辯、不臆造」的照護哲學一致。

## 2. 目標與非目標

### 目標
- 當長期記憶存在互斥事實時，照護 agent 依**最新自述**回應。
- 不摧毀長輩自述歷史（家屬／臨床可回溯）。
- 不在對話熱路徑（每則使用者訊息都會跑 `agent.recall`）新增任何 LLM 呼叫或 DB 查詢。

### 非目標
- 不改 Mem0 寫入路徑（維持 append-only / ADD-only）。
- 不刪除或覆蓋任何長期記憶事實。
- 不改 `provenance.CUSTOM_FACT_EXTRACTION_PROMPT`（非此問題的施力點）。
- 不動 DB／schema／環境變數／依賴套件／mem0 設定。

## 3. 方案取捨（已決策）

| 決策點 | 選項 | 決定 |
|---|---|---|
| 矛盾保存政策 | 讀取時消解（append-only）／寫入時刪覆／軟刪除標記 | **讀取時消解、保留舊事實** |
| 消解機制 | 輕量 prompt 標日期+規則／每輪 LLM 濾除／embedding 群聚 | **輕量 prompt 標日期+規則** |

被否決的替代方案：

- **寫入時刪/覆蓋**：庫乾淨，但失去長輩偏好變化歷史（對認知照護可能具臨床意義）、多一次 LLM 呼叫、刪除不易復原。
- **embedding 群聚+recency**：無額外 LLM 呼叫，但「相似 ≠ 矛盾」，可能誤合併「糖尿病／高血壓」這類相近但不同的健康事實，照護風險高。
- **改用舊版 mem0 取回 UPDATE/DELETE 路徑**：無 config 欄位、路徑未接線；等同降版，依賴風險高，否決。

## 4. 架構與資料流

消解只發生在單一 seam：`Mem0LongTermStore` 的格式化階段。理由：矛盾只存在於長期記憶事實；藥物／回診等 `FactProvider` 是結構化權威資料，不受此規則影響。`recall.py`、`agent.py`、`consolidation.py`、mem0 設定皆不動。

```
agent.recall(line_user_id, query)                         ← 不變
  → Mem0LongTermStore.search(line_user_id, query)
      → _search_raw(使用者 query)  +  _search_raw(HEALTH_QUERY)   ← 不變
      → _dedup                                                    ← 不變
      → 【新增】依 created_at 由新到舊排序
      → _format_memories_for_prompt
           ├─【新增】每筆標記錄日期
           └─【改】前言 _PREFIX 加「新覆舊」規則
  → 拼進 system prompt                                     ← 不變
```

## 5. 具體變更（全部在 `src/kinsun/memory/longterm/store.py`）

1. **帶出 recency**：`search()` 回傳的每筆 mem0 item 本就含頂層 `created_at` 與 `metadata.provenance`（已驗證 `mem0 2.0.10` search 會把 `created_at` 提升為 item 頂層欄位），格式化前不再丟棄。

2. **由新到舊排序**：`_dedup` 後、格式化前，依 `created_at` 遞減排序。缺 `created_at` 者排最後（視為最舊）。排序須容忍 `None`／缺值不崩。

3. **每筆標日期**：括號註記由 provenance 標籤與日期兩段動態組成，四種組合皆須正確：
   - 兩者皆有：`- {事實}（{provenance 標籤}·{YYYY-MM-DD}）`
   - 僅 provenance：`- {事實}（{provenance 標籤}）`（同現行輸出，維持相容）
   - 僅日期：`- {事實}（{YYYY-MM-DD}）`
   - 皆無：`- {事實}`（不留空括號）

   日期取 `created_at` 的日期部分（ISO 字串前 10 碼，即 `YYYY-MM-DD`）。

4. **前言規則**：`_PREFIX` 擴充為（維持照護語氣、與抽取 prompt 第 3 條一致）：

   > 以下為這位長者的長期記憶（部分為長者自述、未必經確認，請勿當成醫療診斷）；已由新到舊排列並附記錄日期。若前後有矛盾，請以較新的記錄為準，並顧及長者感受、不主動糾正；日期僅供你判斷新舊，回覆時不必提及：

## 6. 正確性與邊界

- **不丟非矛盾舊事實**：只重排＋標註，**不過濾任何事實**；舊的健康事實（如「糖尿病」）照樣進 prompt。矛盾取捨交由主 LLM 依規則判斷。此舉刻意避免「因較舊就被丟棄」誤傷重要健康資訊。
- **ISO 日期排序**：mem0 存 ISO-8601（UTC），字串字典序即時間序；仍以「缺值排最後」防呆。
- **失效退化**：`_search_raw` 既有 try/except 不變；排序與格式化不新增可中斷對話的例外。單筆缺欄位以防禦式取值處理。
- **成本**：零額外 LLM 呼叫、零額外 DB 查詢、零新依賴、零 schema 變更。
- **殘留風險（已知並接受）**：舊事實仍在 prompt 內，理論上主 LLM 仍可能引用；此為「輕量方案」的取捨。若日後實測發現洩漏明顯，再升級為「每輪 LLM 濾除」機制（本設計不預先實作，避免過早最佳化）。

## 7. 測試

延伸 `tests/test_longterm_store.py`，沿用現有 `_FakeMem0` / `_ByQueryMem0`：

- `test_format_orders_newest_first`：亂序 `created_at` 的多筆 → 輸出新在前。
- `test_format_annotates_date`：日期（`YYYY-MM-DD`）出現在對應行。
- `test_format_prefix_has_recency_rule`：前言含「以較新的記錄為準」。
- `test_format_missing_created_at_no_crash`：缺 `created_at` 的筆仍正常輸出且排最後、不崩。
- 既有測試（斷言 `長者自述`／`有高血壓` 等子字串）維持通過。
- 全套 `uv run pytest` 綠燈。

人工驗證：對「壽司/麥當勞」測試帳號重跑一次 recall，確認記憶區塊「麥當勞」排在「壽司」前、且含新覆舊規則。

## 8. 文件同步

本變更不涉及 API／環境變數／DB schema／對外介面，`.env.example` 無需更動。長期記憶行為的說明以本設計文件為準。
