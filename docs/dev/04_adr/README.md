# ADR 索引

> 一個決策一份 ADR。狀態：已接受＝人工拍板（註記人＋日期）。
> 全部經 2026-07-07/08 逐項重新確認（含程式碼已成形的抉擇），非沿用舊文件結論。

| ADR | 標題 | 狀態 | 關聯決策 |
| :--- | :--- | :--- | :--- |
| [001](ADR-001-後端框架FastAPI.md) | 後端框架：Python＋FastAPI＋uv | 已接受 | — |
| [002](ADR-002-資料庫Supabase-Postgres.md) | 資料庫與儲存：Supabase Postgres＋pgvector＋Storage | 已接受 | 音檔公開 bucket 疑慮另列 13 循環 |
| [003](ADR-003-長期記憶Mem0.md) | 長期記憶：Mem0 v1.1 | 已接受 | — |
| [004](ADR-004-知識圖譜移除與拆解.md) | 知識圖譜（Neo4j）移除與四用途拆解 | 已接受 | D-17 |
| [005](ADR-005-LLM模型策略.md) | LLM 模型策略：開發期免費模型、上線前升級關鍵路徑 | 已接受 | D-16 |
| [006](ADR-006-自建排程器.md) | 自建排程器（croniter＋Postgres 持久化） | 已接受 | — |
| [007](ADR-007-語音服務自架DGX.md) | 語音服務自架 DGX（Breeze-ASR-26／CosyVoice 3） | 已接受 | D-01 |
| [008](ADR-008-前端技術組合.md) | 前端技術組合（React＋Vite／Expo） | 已接受 | D-08 |
| [009](ADR-009-家屬雙認證並存.md) | 家屬雙認證並存（App token＋LIFF idToken） | 已接受 | LINE 退場時機待議 |
| [010](ADR-010-單一儲存庫佈局.md) | 單一儲存庫（monorepo）佈局 | 已接受 | — |
| [011](ADR-011-通道中立身分層.md) | 通道中立身分層（elder_id 主鍵＋channel_bindings） | 已接受 | D-08 |
| [012](ADR-012-內測模式後端下發.md) | 內測模式後端單一開關（INTERNAL_TESTING_ENABLED 經公開 meta 下發） | 已接受 | D-73 |
