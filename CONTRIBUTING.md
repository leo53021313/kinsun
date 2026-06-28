# 協作規範（CONTRIBUTING）

本文件說明 **金孫 KinSun** 專案的多人協作流程。所有隊友開始開發前請先讀完本文件。
開發規範（程式碼品質、安全性等）見 [AGENTS.md](AGENTS.md)。

---

## 角色

| 角色 | 負責人 | 職責 |
|------|--------|------|
| 整合負責人（Integrator） | **Leo（@leo53021313）** | 審查所有 PR、合併進 `main`、維護 `main` 品質 |
| 開發成員 | Babic, Brian, Jerry, Kevin, MA, Otto | 在各自分支開發、發 PR |

---

## 分支模型

```
main  ← 唯一正式主幹，受保護，只能透過 PR 合併
 ├─ Babic    ┐
 ├─ Brian    │
 ├─ Jerry    │  每人長期的個人開發分支
 ├─ Kevin    │
 ├─ Leo      │
 ├─ MA       │
 └─ Otto     ┘
```

規則：

* **沒有人可以直接 push 到 `main`**，一律走 Pull Request。
* 每位成員只在「自己名字」的分支上開發。
* `main` 由整合負責人審查後合併。

---

## 開發流程

### 1. 開工前，先把 main 同步進自己的分支

每次開始工作前都做，能大幅減少之後的合併衝突：

```bash
git checkout <你的分支>          # 例如 git checkout Leo
git fetch origin
git merge origin/main           # 把 main 最新進度併進來
```

如果有衝突，**在自己的分支先解決**，不要把衝突帶到 PR。

### 2. 開發並提交

```bash
git add <檔案>
git commit -m "feat: 加入台語語音辨識前處理"
```

* 修改範圍盡量小、聚焦單一任務（見 [AGENTS.md](AGENTS.md)）。
* commit 訊息規範見下方。

### 3. 推送自己的分支

```bash
git push origin <你的分支>
```

### 4. 發 Pull Request：你的分支 → main

* 到 GitHub 開 PR，base 選 `main`，compare 選你的分支。
* 填好 PR 模板（會自動帶出）。
* PR 會自動請 **整合負責人** 審查。

### 5. 審查與合併

* 整合負責人 review，必要時請你修改。
* 通過後由 **整合負責人** 合併進 `main`。

### 6. 合併後，大家重新同步 main

整合負責人合併後會通知大家，每位成員回到步驟 1 把最新的 `main` 併回自己的分支。

---

## Commit 訊息規範

格式：`<type>: <簡短說明>`

| type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修 Bug |
| `docs` | 文件 |
| `refactor` | 重構（不改行為） |
| `test` | 測試 |
| `chore` | 雜項（設定、依賴等） |

範例：

```
feat: 新增 LINE Bot webhook 接收端點
fix: 修正 TTS 在長句子被截斷的問題
docs: 補充環境變數設定說明
```

---

## Pull Request 規範

* 一個 PR 只做一件事，方便審查。
* 標題用 commit 訊息規範格式。
* 描述清楚「做了什麼、為什麼、怎麼測」。
* 合併前確認與 `main` 沒有衝突。

---

## 衝突處理

衝突最常發生在「多人改到同一個檔案」。降低方法：

1. **勤同步 main**（步驟 1），不要讓分支落後太多。
2. 依模組分工，盡量不要動到別人負責的檔案（分工見 [.github/CODEOWNERS](.github/CODEOWNERS)）。
3. 真的要改共用檔案前，先在群組講一聲。

---

## main 分支保護規則

`main` 已在 GitHub 設定保護：

* 禁止直接 push，必須透過 PR。
* PR 需至少 1 位審查者核准才能合併。
* 禁止 force push 與刪除分支。

> 整合負責人（admin）在必要時可繞過上述限制處理緊急狀況。
