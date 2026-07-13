# ADR-003: 長期記憶採 Mem0 v1.1（Gemini＋Supabase pgvector）

> **狀態:** 已接受 | **日期:** 2026-07-08 | **決策者:** Leo（批次重新確認）

## 1. 背景與問題

- **上下文**: 產品承諾「AI 記得住、會回頭關心」——需要跨日的長輩事實記憶（用藥、慢性病、生活事件）。
- **問題**: 自建記憶抽取＋檢索管線工程量大且品質難保證。
- **驅動因素/約束**: 記憶內容含健康隱私（→ 已關閉 mem0 遙測，`mem0_factory.py:44`）。

## 2. 考量的選項

- **Mem0（OSS）**：現成的記憶抽取／檢索框架，LLM 與向量庫可插拔。
- **自建（embedding＋規則抽取）**：曾實作過（61a34be 之前），品質與維護成本差。

## 3. 決策

**選擇**: Mem0 v1.1（LLM＝Gemini、向量庫＝Supabase pgvector），夜間 3:00 整批 consolidation。

**理由**: 自建版已實測淘汰；Mem0 提供現成的「LLM 事實抽取＋去重＋ADD-only 儲存＋語意檢索」管線。
（2026-07-08 查證修正：entity linking／BM25 多訊號檢索在本專案組態**未生效**——Supabase 後端無 keyword_search、spaCy 未安裝；~~reranker 未啟用~~ → 丁-4（2026-07-09）起 LLM reranker（gemini）＋explain 預設啟用（✅ 庚-54 更新；D-40 Leo 已確認）。其餘仍為純語意單路檢索。provenance 補述：FAMILY_CONFIRMED 與 INFERRED 均無寫入路徑（D-37 保留定義暫不接線）。詳見 `.claude/context/decisions/explore-2026-07-08-0930-mem0功能落差查證.md`；檢索增強取捨將於 07 模組循環登記決策。）

## 4. 後果

- **正面**: 記憶三層（短期／長期／事實）架構清晰，`SessionMemory.assemble` 單一門面。
- **負面**: 依賴 Mem0 版本行為（v1.1 釘版）；provenance 的 `family_confirmed` 尚無寫入路徑（後續循環議）。
- **重新評估觸發**: Mem0 大版本變更；記憶品質實測不達標時。
