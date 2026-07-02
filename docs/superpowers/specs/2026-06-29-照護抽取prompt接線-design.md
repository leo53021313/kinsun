# 照護抽取 prompt 接線（custom_instructions）設計

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：⑦ 記憶／資料層（長期記憶骨幹 Mem0-g）。
> 前置模組：[記憶層雲端遷移](2026-06-29-記憶層雲端遷移-design.md)。
> 借鏡來源：mem0 原始碼（`mem0ai` 2.0.10，本機 `temp/` 參考、不進版控）。
> 本案為「Hermes / Mem0 借鏡與優化」系列第 1 項（T1.1）。

---

## 1. 背景與目標

[provenance.py](../../../src/kinsun/longterm/provenance.py) 定義了照護抽取紀律 prompt `CUSTOM_FACT_EXTRACTION_PROMPT`（自述≠診斷、不替長者下醫療判斷、對認知退化矛盾不臆造、只抽穩定事實），**但全專案沒有任何地方使用它**——目前 [Mem0LongTermStore.add](../../../src/kinsun/longterm/store.py) 只傳 `metadata`，[mem0_factory.py](../../../src/kinsun/mem0_factory.py) 的 config 也未帶任何自訂抽取設定。等於 Mem0 一直用**預設抽取 prompt** 在抽取長者的長期記憶，照護紀律從未生效。

本案把這段紀律真正接上 Mem0：在 Mem0 config 設 `custom_instructions`，讓它在每次記憶抽取時作為最高優先級規則套用。

**完成後：** 每日整理（consolidation）寫入長期記憶時，Mem0 的事實抽取會帶上照護紀律約束。單元測試保證「設定確實接上」；抽取品質的實機效果留待雲端冒煙測試驗證（見 §6）。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* [mem0_factory.py](../../../src/kinsun/mem0_factory.py) `build_mem0_config(settings)` 的回傳 dict 新增頂層 key `custom_instructions`，值為 `provenance.CUSTOM_FACT_EXTRACTION_PROMPT`（**原文逐字**）。
* 對應單元測試（離線）。

### 2.2 不在範圍內（後續項目）
* **結構化分類 / category metadata**、關鍵事實每輪必帶 → T1.2。
* **Mem0 版本升級、新演算法路徑、graph 關係檢索** → MEM-UP。
* per-call 的 `add(prompt=...)`（本案採 config 層級，一次設定全域生效）。
* 改寫 `CUSTOM_FACT_EXTRACTION_PROMPT` 文字內容（決策：逐字接上）。

---

## 3. 機制（經查 mem0 2.0.10 原始碼）

* `MemoryConfig` 有頂層欄位 `custom_instructions: Optional[str]`（`mem0/configs/base.py`）；`Memory.__init__` 讀進 `self.custom_instructions`（`mem0/memory/main.py`）。
* 抽取時，`custom_instructions` 被當成**最高優先級的附加規則**，插進預設抽取 prompt 的 `## Custom Instructions` 段（`mem0/configs/prompts.py`）——**疊加**而非取代預設 prompt。
* 輸出格式（JSON / `facts`）由 Mem0 預設 prompt 負責；`ensure_json_instruction`（`mem0/memory/utils.py`）會在偵測不到 `json` 字樣時自動補上 JSON 指令。**結論：逐字接上即安全，無須我方對齊輸出格式。**

```python
# mem0_factory.py（變更後）
def build_mem0_config(settings: Settings) -> dict:
    return {
        "llm": {...},
        "embedder": {...},
        "vector_store": {...},
        "graph_store": {...},
        "custom_instructions": provenance.CUSTOM_FACT_EXTRACTION_PROMPT,  # 新增
    }
```

`mem0_factory.py` 需 `from kinsun.longterm import provenance`（或 `import ... as prov`）。`build_mem0_memory` 不變（仍 `Memory.from_config(build_mem0_config(settings))`）。

---

## 4. 元件與介面

* 無新元件、無新 Protocol、無新環境變數、無新依賴、無資料表變更。
* 唯一改動點：`build_mem0_config` 多一個 key。`Mem0LongTermStore`、`consolidation`、`app.py`、`scheduler` 一律不動（它們都經由 `build_mem0_memory` 取得已帶 `custom_instructions` 的 Memory）。

---

## 5. 錯誤處理（fail-safe）

* 本案只是多帶一個 config 字串，不改任何讀寫路徑、不改控制流；既有的 `Mem0LongTermStore.search`/`add` fail-safe（檢索失敗退化為空、不中斷對話）完全保留。
* `custom_instructions` 為 Mem0 既有合法欄位；即使未來 Mem0 行為改變而忽略它，也只是「紀律未生效」退回現狀，不會崩潰。
* secret 不受影響（仍全走環境變數）。

---

## 6. 測試策略（單元全離線，整合 opt-in）

* `tests/test_mem0_factory.py` 既有測試補一條：`build_mem0_config(settings)` 的回傳含 key `custom_instructions`，且其值 `== provenance.CUSTOM_FACT_EXTRACTION_PROMPT`（驗證「確實接上、且為原文」）。
  * 不呼叫真 Mem0、不需金鑰；沿用既有以假 `Settings` 組 config 的測試方式。
* **抽取品質實機驗證（deferred）**：實際「照護紀律是否改變抽取結果」需 Gemini + 雲端，列為雲端冒煙測試項目，於 MEM-UP（金鑰到位）時一併驗證。本案不在 CI 內跑真抽取。

---

## 7. 已知取捨（列出供否決）

* **採 config 層級 `custom_instructions` 而非 per-call `add(prompt=...)`**：一次設定全域生效、改動最小、與「組裝根集中設定」一致；代價是無法逐次客製（本專案不需要）。
* **逐字接上、不改 prompt 文字**：最小修改、保留你原本的照護用語；代價是開頭「你負責從…抽取…」這類框架語句與 Mem0 預設職責略有重疊（無害，僅語氣冗餘）。
* **抽取效果不在單元測試內驗證**：受限於需雲端/金鑰；以「設定接上」為本案驗收，效果驗證延後且明確記錄，不假裝已驗證。
