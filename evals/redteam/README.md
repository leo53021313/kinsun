# redteam — promptfoo 紅隊掃描

用 [promptfoo](https://github.com/promptfoo/promptfoo)（MIT，Node CLI）自動生成攻擊題，
打我們**真正的 CareAgent**。與 `evals/experiments/prompt_injection.py` 分工如下：

| | Opik 注入評測 | promptfoo 紅隊 |
| :--- | :--- | :--- |
| 題目 | 手寫 32 題（固定、可回歸比對） | 自動生成數百題（每次不同） |
| 量什麼 | 攔截率 **＋誤殺率**（8 題 benign 對照組） | 只量攻擊成功率 |
| 跑的頻率 | 常態（改 prompt／改審核就跑） | 偶爾深掃 |
| 定位 | 品質關卡 | **攻擊靈感來源** |

**兩者不可互相取代。** promptfoo 不量誤殺，而誤攔一句長輩閒聊對本產品是比放過一次
綁架更嚴重的缺陷——那件事只有 Opik 那條的 benign 對照組在守。

建議用法：跑一輪紅隊 → 挑出**真的打穿**的攻擊 → 翻寫成中文情境補進
`evals/datasets/prompt_injection.py` → 日常仍跑 Opik 那條。這樣拿到攻擊廣度，
又不必長期維護兩套評測。

## 前置

- Node.js `>=22.22`（本機實測 v24 可用）。**不需要安裝**，走 `npx`。
- 不進 `pyproject.toml`、不進任何 `package.json`——這是偶爾跑的工具，不是專案依賴。
- Python 端沿用本 repo 的 `.venv`（provider 會自己補 `sys.path`，不必設 `PYTHONPATH`）。

## 執行

```bash
cd evals/redteam

# ① promptfoo 的 google provider 讀 GOOGLE_API_KEY，不是我們慣用的 GEMINI_API_KEY。
#    這一步必須做，否則攻擊生成會退回找 OPENAI_API_KEY 然後失敗。
export GOOGLE_API_KEY="$GEMINI_API_KEY"

# ② 指定用本 repo 的 venv 跑 provider.py（否則 promptfoo 會抓系統 python，匯入不到 kinsun）
export PROMPTFOO_PYTHON="$(cd ../.. && pwd)/.venv/bin/python"

# ③ 紅隊的幾百筆 trace 不必洗進 Opik 專案
export OPIK_ENABLED=false

# ④ 生攻擊題並執行（結果寫 redteam.yaml，另存一份 output.json）
npx promptfoo@latest redteam run --output output.json

# ⑤ 看報告（本機網頁介面）
npx promptfoo@latest redteam report
```

要順便量「開了審核擋不擋得住」，加 `SAFETY_MODERATION_ENABLED=true` 再跑一次即可
（provider 走 `evals/subject.py`，與正式管線同一套判斷）。

## ⚠️ 三個踩雷點

### 1. 不要開 `harmful:*` 系列 plugin

promptfoo 的預設評分邏輯假設「拒絕談有害話題＝好」。**對這個產品是反的**：長輩說
「我不想活了」時，溫柔回應並建議聯絡家人是**正確且必要**的行為，拒答才是缺陷。
開 `harmful:self-harm` 之類的 plugin，會把我們設計對的行為判成漏洞，數字完全誤導。

同理由，`promptfooconfig.yaml` 的 `purpose` 最後一句刻意寫明這件事，讓攻擊生成器
不要把「願意談情緒困擾」當成要攻破的弱點。

### 2. 一定要留著 `language: zh-TW`

預設生英文攻擊。英文攻擊測得到模型底層韌性，但測不到我們真正的風險面——使用者是
講中文的台灣長輩，真實攻擊也會是中文的。拿掉這行等於在測一個不存在的威脅模型。

### 3. 免費層額度會擋住你

實測 Opik 那條跑 32 題就花 8 分 41 秒，且有 5～11 題的裁判呼叫被 429 擋掉、**根本沒
評到分**。紅隊預設題量遠大於此（`numTests × plugin 數 × strategy 數`），現在的設定
已刻意壓到 `numTests: 3`、只開兩個 strategy。要開 `crescendo`／`base64`／
`jailbreak:composite` 之前，先換付費金鑰。

`provider.py` 把單題例外轉成 `{"error": ...}` 回報而非往外拋，所以撞到限流只會讓
該題標記失敗，不會中止整輪掃描——但失敗題數多的時候，報告上的比率就不可信了，
看報告前先確認失敗題數。

## 檔案

- `provider.py`——promptfoo 的自訂 Python provider，經 `evals/subject.py` 驅動真 CareAgent。
  含**多輪對話解析**（`parse_turn`）：crescendo 這類 strategy 傳來的是 JSON 對話陣列，
  必須讓整串對話共用同一個 `elder_id`，短期記憶才累積得起來。⚠️ 這件事沒做對，多輪
  測試會**靜默**退化成單輪（每輪換一位長輩）——測起來全綠，但整條攻擊面根本沒碰到。
  由 `tests/test_evals_redteam_provider.py` 守住，且設定中的 `workers: 1` 不可拿掉。
- `assert_speakable.py`——確定性 assertion（回覆能不能唸給長輩聽），規則本體在
  `evals/assertions.py`，與 Opik 評測共用。不呼叫 LLM，不吃額度。
- `promptfooconfig.yaml`——攻擊生成設定（模型／語言／purpose／plugins／strategies）。
- `redteam.yaml`、`output.json`——執行後產生的**結果檔，不進版控**（見 `.gitignore`）。

## 多輪綁架（crescendo）

`crescendo` 已預設開啟：先閒聊幾輪建立信任，再把要求慢慢推過界。這是我們覆蓋面最大的
洞——Opik 那條注入評測是**單輪**的，而正式管線的短期記憶會把前幾輪帶進 system prompt，
等於這條路徑從沒被攻擊過。代價是每題要跑多輪對話，額度消耗遠高於 `basic`／`jailbreak`，
免費層請留意失敗題數。
