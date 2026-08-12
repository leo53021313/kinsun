# Kinsun 長輩陪伴對話：主持指南

> 版本：v1.0｜日期：2026-07-27｜狀態：待真人場次
> 研究範圍：雙手勢可發現性、Listening／Thinking／Speaking 辨識、連線錯誤回復。

## 1. 測試前準備

- 目標時間：每場 20–25 分鐘。
- 使用同一公開 Prototype：[開啟待機畫面](https://kinsun-akin-prototype.princejerrywu.chatgpt.site/?research_state=idle)。
- 準備 [單場觀察表](../usability-observation-sheet.md)；參與者只使用 `P01` 這類代碼。
- 將招募、聯絡與同意資料留在 repo 外的核准位置。
- 除非另有獨立同意，不錄音、不錄影，也不輸入真實健康內容。
- 測試的是產品，不是受試者；受試者可跳過問題或隨時停止。

## 2. 開場與同意口述

主持人照以下意思說明，不必逐字背誦：

> 今天想請您試用一個還在設計中的陪伴對話畫面。我們是在測試畫面，不是在測試您。畫面不會真的錄音，也不會送出您說的內容。我會記錄操作方式與您對畫面的理解，不記姓名、電話或健康資料。過程中若不想繼續，可以隨時停止。您同意現在開始嗎？

未取得同意就不開始，並在 repo 外的研究紀錄中處理同意狀態。

## 3. 提示層級

每個任務由 0 開始，只在受試者停住約 10 秒或主動求助時往下一級：

| 層級 | 主持方式 | CSV |
| --- | --- | --- |
| 0 | 不提示，只重述任務目標。 | `assistance_level=0` |
| 1 | 「請看看畫面上有沒有可以幫忙的提示。」 | `assistance_level=1` |
| 2 | 直接說明可使用最大的圓形麥克風與對應手勢。 | `assistance_level=2` |
| 3 | 直接說明後仍無法完成、受試者停止，或主持人因安全／挫折中止。 | `assistance_level=3`、`not_completed` |

不要指按鈕、替受試者操作，或在任務前讀出狀態名稱。

## 4. 任務腳本

### 任務 A：自然開始一段對話

1. 開啟[待機畫面](https://kinsun-akin-prototype.princejerrywu.chatgpt.site/?research_state=idle)。
2. 說：「請跟阿金說，您今天早餐吃了什麼。」
3. 不提示按法；記錄第一個自行採用的手勢、首次操作時間、是否誤送／漏送與協助層級。

### 任務 B：使用另一種說話方式

依任務 A 的首選手勢，請受試者改用另一種：

- 若任務 A 先短按：說「這一次請按住說話，說完再放開。」
- 若任務 A 先按住：說「這一次請按一下開始，說完再按一下。」
- 若任務 A 無法判定：依參與者代碼奇偶交錯順序；奇數先教短按，偶數先教按住。

完成後詢問：「剛才這個方式對您來說，1 分非常困難、5 分非常容易，您會給幾分？」不追問偏好理由到引導答案。

### 任務 C：辨識系統狀態

依序開啟固定畫面，每次只問：「您覺得阿金現在正在做什麼？」只記受試者原意，不先讀出畫面文字：

1. [短按後正在聽](https://kinsun-akin-prototype.princejerrywu.chatgpt.site/?research_state=listening-tap)
2. [按住時正在聽](https://kinsun-akin-prototype.princejerrywu.chatgpt.site/?research_state=listening-hold)
3. [正在處理](https://kinsun-akin-prototype.princejerrywu.chatgpt.site/?research_state=thinking)
4. [正在回答](https://kinsun-akin-prototype.princejerrywu.chatgpt.site/?research_state=speaking)

CSV 的 Listening 只記受試者是否理解「系統仍在聽」；兩種 Listening 的差異寫在 `observation`。

### 任務 D：從連線錯誤回復

1. 開啟[連線錯誤畫面](https://kinsun-akin-prototype.princejerrywu.chatgpt.site/?research_state=error)。
2. 說：「剛才好像沒有成功，請您看看接下來會怎麼做。」
3. 記錄是否完成重新連線、回到待機或未完成；不要預先說出按鈕名稱。

## 5. 收尾問題

只在四個任務完成後詢問：

1. 「哪一種說話方式比較順？為什麼？」
2. 「剛才有哪個畫面讓您不知道要等、要說話，還是要按按鈕？」
3. 「如果只能改一件事，您會希望改什麼？」

這些回答只作質性脈絡，不以單一受試者偏好直接改版。

## 6. 每場結束後

1. 完成 [單場觀察表](../usability-observation-sheet.md)。
2. 依 [資料字典](data-dictionary.md) 將 A–D 各轉成一列，附加到 `research-sessions.csv`。
3. 人工確認沒有個資、健康內容或逐字稿。
4. 在 repo root 執行：

```powershell
python docs/uiux/prototype/tools/summarize_usability_results.py
```

5. 開啟 [跨場次彙整](research-summary.md)，只把重複行為與明確阻塞寫入研究者解讀；不要把自動計數改寫成虛構洞察。

## 7. 暫停與升級條件

出現以下任一情況，停止該任務並標記 `critical_issue=yes`：

- 受試者明顯不適、焦慮或要求停止。
- 不知道系統是否仍在聆聽，造成持續說出不想送出的內容。
- 主要手勢無法完成，且直接說明後仍阻塞。
- 錯誤狀態找不到任何可理解的回復方式。

第一個 P0 出現時先回看錄入與 Prototype 是否一致；若確認為設計問題，先修正再擴大招募。
