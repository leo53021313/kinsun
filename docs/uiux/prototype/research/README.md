# Kinsun 陪伴對話可用性研究包

> 版本：v1.0｜日期：2026-07-27｜狀態：可執行，尚無真人研究資料

這個目錄把公開 Prototype、主持腳本、去識別資料格式與跨場次彙整接成同一條流程。它不包含招募名單、同意資料、個資、健康內容、錄音或虛構研究結果。

## 執行入口

1. 先閱讀 [主持指南](moderator-guide.md)。
2. 使用[公開待機畫面](https://kinsun-akin-prototype.princejerrywu.chatgpt.site/?research_state=idle)開始每一場。
3. 逐場填寫 [觀察表](../usability-observation-sheet.md)。
4. 依 [資料字典](data-dictionary.md) 把每位參與者的 A–D 任務附加到 `research-sessions.csv`。
5. 執行彙整工具，更新 [研究摘要](research-summary.md)。

```powershell
python docs/uiux/prototype/tools/summarize_usability_results.py
```

## 檔案責任

| 檔案 | 用途 | 是否可放真人資料 |
| --- | --- | --- |
| `moderator-guide.md` | 20–25 分鐘主持腳本、固定狀態連結、提示層級 | 否 |
| `data-dictionary.md` | CSV 欄位、代碼、一致性與隱私規則 | 否 |
| `research-sessions.csv` | 去識別化任務紀錄；目前只有表頭 | 僅限通過規則的去識別資料 |
| `research-summary.md` | 工具產生的描述性計數與研究者待填區 | 僅限去識別彙整 |
| `../usability-observation-sheet.md` | 單場紙本或暫存模板 | 不得直接提交含個資版本 |

## 證據門檻

- 0 場：只能說「尚無研究結論」。
- 少於 5 場完整測試：只能視為提前訊號，用於找問題。
- 5–6 場完整測試：可作第一輪質性主題分析，不代表統計顯著或所有長輩。
- 任何主張都要能回到去識別任務列與單場觀察；不能由 Proto-persona、主持人印象或自動摘要取代。
