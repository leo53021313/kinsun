# 可用性測試資料字典

> 版本：v1.0｜日期：2026-07-27｜狀態：可執行

`research-sessions.csv` 每列代表一位去識別參與者的一個任務。欄位值採固定英文代碼，方便驗證與彙整；主持與分析文件維持台灣繁體中文。

## 欄位

| 欄位 | 必填 | 允許值／格式 | 說明 |
| --- | --- | --- | --- |
| `participant_id` | 是 | `P01`–`P999` | 研究代碼，不放姓名或聯絡方式。 |
| `session_date` | 是 | `YYYY-MM-DD` | 測試日期。 |
| `device` | 是 | 去識別文字 | 例如 `iPhone 13`、`Pixel 8`；不寫裝置擁有人。 |
| `font_scaling` | 是 | 去識別文字 | 例如 `default`、`large`、`unknown`。 |
| `task_id` | 是 | `A`、`B`、`C`、`D` | 對應測試計畫四項任務。 |
| `completion` | 是 | `completed`、`not_completed` | 任務是否完成。 |
| `assistance_level` | 是 | `0`、`1`、`2`、`3` | 0 無協助；1 一次中性提示；2 直接說明；3 未完成。 |
| `duration_seconds` | 否 | 0 以上數字 | 從任務說明結束到完成／停止的秒數。 |
| `first_gesture` | 任務 A 必填 | `tap`、`hold`、`undetermined` | 任務 A 第一個自行採用的手勢；其他任務留空。 |
| `error_count` | 是 | 0 以上整數 | 誤送、漏送、重覆按壓或中斷總次數。 |
| `ease_score` | 否 | 1–5 | 1 非常困難、5 非常容易；拒答時留空。 |
| `listening_correct` | 任務 C 必填 | `yes`、`no`、`uncertain` | 是否理解正在聆聽。 |
| `thinking_correct` | 任務 C 必填 | `yes`、`no`、`uncertain` | 是否理解正在處理。 |
| `speaking_correct` | 任務 C 必填 | `yes`、`no`、`uncertain` | 是否理解正在回答。 |
| `error_recovery` | 任務 D 必填 | `reconnected`、`returned_idle`、`not_completed` | 錯誤回復結果。 |
| `critical_issue` | 是 | `yes`、`no` | 是否阻止核心任務或造成明顯不安／誤解。 |
| `observation` | 否 | 單行去識別文字 | 只記行為與短句，不記健康內容或身分資料。 |

## 一致性規則

- `completed` 只能搭配協助層級 0–2；`not_completed` 必須搭配層級 3。
- 同一參與者的日期、裝置與字級設定需一致。
- 同一參與者的同一任務只能有一列。
- 一場完整測試應有 A、B、C、D 四列；工具允許暫存不完整場次，但會分開計數。

## 隱私界線

- 不得進版控：姓名、電話、電子郵件、地址、帳號、真實健康敘述、錄音或逐字稿。
- 招募名單、同意紀錄與聯絡資料應留在經核准的研究儲存位置，不得放進此 repo。
- 彙整工具會阻擋明顯電子郵件與台灣手機號碼，但無法判斷所有個資或健康資訊；匯入前仍需人工檢查。
