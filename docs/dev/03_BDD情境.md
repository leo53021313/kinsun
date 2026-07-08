# BDD 情境 - 金孫 KinSun

> **版本:** v1.0 | **更新:** 2026-07-07 | **狀態:** 待議中（部分情境掛 ⚠ 決策標籤）
> **對應:** [02_專案簡報與PRD](02_專案簡報與PRD.md) 的 Epic A–E；決策編號見 [00_決策清單](00_決策清單.md)。
> **標籤約定:** `@as-is`＝現況已實作且行為如述；`@to-be`＝已拍板、重構後達成；`@pending-decision-Dxx`＝行為細節待決議，情境為佔位草稿，決議後改寫。

---

## talk.feature — 長輩語音／文字對話（Epic A）

```gherkin
Feature: 長輩與金孫對話
  # 對應 PRD: US-A1, US-A2, US-A3

  Background:
    Given 長輩「阿蘭」的裝置已由家屬完成綁定
    And 阿蘭的知情同意有效

  @as-is @happy-path @smoke-test
  Scenario: App 對講機語音回合
    When 阿蘭按住麥克風說「今天天氣不錯」並放開
    Then 她應該在同一回應中收到文字與語音回覆
    And 回覆語音應自動播放
    And 這一輪對話應寫入今日短期記憶

  @as-is @sad-path
  Scenario: 撤回同意後語音被拒
    Given 阿蘭的知情同意已撤回
    When 阿蘭的裝置送出語音
    Then 系統應回覆 403 consent_revoked
    And 不應產生任何對話紀錄

  @as-is @edge-case
  Scenario: 音檔超過大小上限
    When 阿蘭的裝置送出超過 10MB 的音檔
    Then 系統應回覆 413
    # 10MB 上限為現況值，後續 06 API 循環複核

  @to-be @happy-path
  Scenario: 打字與語音同等對待（✅ D-11）
    When 阿蘭打字「最近都睡不好」
    Then 金孫應該像語音一樣回覆她
    And 這段文字應經過危急偵測
    And 這一輪對話應寫入今日短期記憶

  @to-be @happy-path
  Scenario: 台語對話（✅ D-01，TTS 微調完成後驗收）
    When 阿蘭用台語說「我今仔日人無爽快」
    Then 語音辨識應正確轉寫她的話
    And 金孫應以台語語音回覆
```

---

## safety.feature — 危急偵測與家屬通知（Epic B）

```gherkin
Feature: 危急偵測分級與通知
  # 對應 PRD: US-B1, US-B2

  Background:
    Given 長輩「阿蘭」已綁定且同意有效
    And 阿蘭有兩位已綁定的家屬

  @as-is @happy-path @smoke-test
  Scenario: 絕對危急詞觸發 L3
    When 阿蘭說「救命」
    Then 應記錄一筆 L3 危急事件
    And 家屬應收到含「撥打 119」提示的通知
    And 通知應先於回覆生成（回覆失敗也不影響通知）

  @as-is
  Scenario: 症狀詞觸發 L2
    When 阿蘭說「我今天有點頭暈」
    Then 應記錄一筆 L2 危急事件
    And 家屬應收到關懷提醒通知

  @pending-decision-D10
  Scenario: 通知對象、冷卻與升級（⚠ 7/8 會議後改寫）
    # 現況：L2+ 即時通知全部家屬、無冷卻無去重。
    # 會議決議後補：冷卻窗？逐級升級（escalation_order）？L1 是否彙整？
    Given 阿蘭在十分鐘內連續三次提到「跌倒」
    When 危急偵測連續觸發
    Then 通知行為依 D-10 決議

  @to-be
  Scenario: 打字求救進安全網（✅ D-11）
    When 阿蘭打字「我想不開」
    Then 應與語音同等分級並記錄危急事件
    And 家屬應照常收到通知

  @to-be
  Scenario: 純 App 家屬收到警報（✅ D-12）
    Given 家屬只使用 App、未綁定 LINE
    When 阿蘭觸發 L2 以上危急事件
    Then 家屬開啟 App 應能看到該警報
    # 真推播於階段 5（D-08）後補：不開 App 也能收到

  @pending-decision @sad-path
  Scenario: LLM 分級器故障時的安全網（⚠ 後續 07 模組循環議 fail-safe 方向）
    # 現況：Gemini 失敗一律 L0（不通知、只記 log），故障期間僅剩關鍵詞守門。
    Given 危急分級 LLM 服務故障
    When 阿蘭說出不含關鍵詞的危急語意
    Then 系統行為依後續決議
```

---

## reminders.feature — 用藥與回診提醒（Epic C）

```gherkin
Feature: 用藥與回診提醒
  # 對應 PRD: US-C1, US-C2

  @as-is @happy-path
  Scenario: 用藥時段提醒
    Given 家屬已為阿蘭設定早上時段的血壓藥
    And 阿蘭的知情同意有效
    When 早上提醒時段到達
    Then 阿蘭應收到含藥名的提醒訊息

  @as-is @sad-path
  Scenario: 未同意不發用藥提醒
    Given 阿蘭的知情同意已撤回
    When 任一用藥提醒時段到達
    Then 阿蘭不應收到提醒

  @as-is @happy-path
  Scenario: 回診雙窗提醒
    Given 阿蘭明天有回診「心臟科」
    When 回診提醒時段到達
    Then 阿蘭應收到回診提醒
    And 全部家屬也應收到回診提醒
    # ⚠ 家屬端提醒不受同意約束——此差異後續 07 模組循環登記決策

  @to-be
  Scenario: 純 App 使用者收到提醒（✅ D-12）
    Given 阿蘭與家屬皆只使用 App
    When 任一提醒觸發
    Then 開啟 App 應能看到提醒紀錄
```

---

## accounts.feature — 帳號、綁定與同意（Epic D）

```gherkin
Feature: 家屬帳號與長輩裝置綁定
  # 對應 PRD: US-D1, US-D2

  @as-is @happy-path @smoke-test
  Scenario: 家屬註冊並登入
    When 家屬以 email 與密碼註冊
    Then 應建立家屬帳號並取得 API token
    And 用同一組帳密登入應成功

  @as-is @sad-path
  Scenario: 登入失敗不洩露帳號存在性
    When 有人以不存在的 email 登入
    Then 錯誤訊息不應透露該 email 是否註冊過

  @as-is @happy-path
  Scenario: 綁定碼開通長輩裝置
    Given 家屬為阿蘭產生了綁定碼
    When 長輩裝置以綁定碼開通
    Then 裝置應取得長期 token
    And 應留存代理同意（PROXY）紀錄

  @as-is @edge-case
  Scenario Outline: 邀請碼失效
    Given 一組邀請碼 <狀態>
    When 有人嘗試兌換
    Then 兌換應失敗且提示 <訊息>

    Examples:
      | 狀態         | 訊息     |
      | 已超過有效期 | 已過期   |
      | 已被兌換     | 已被使用 |

  @pending-decision-D13
  Scenario: 撤回同意入口（⚠ 7/8 會議後改寫）
    # 現況：服務層有 revoke_consent，但全系統無任何入口。
    # 會議決議後補：入口放哪端？撤回時是否提供資料刪除選項（與 D-14 連動）？
    When 阿蘭或家屬想撤回知情同意
    Then 撤回途徑與資料處置依 D-13 決議
```

---

## reports.feature — 家屬健康報告（Epic D）

```gherkin
Feature: 家屬查看長輩健康報告
  # 對應 PRD: US-D3

  @as-is @happy-path
  Scenario: 近 30 天健康報告
    Given 家屬已綁定阿蘭
    When 家屬開啟阿蘭的健康報告
    Then 應看到近 30 天的危急事件與提醒紀錄
    # 30 天窗與內容顆粒度 ⚠ D-09 會議後複核

  @pending-decision-D09
  Scenario: 家屬可見範圍邊界（⚠ 7/8 會議後改寫）
    # 候選：維持警報＋報告／開放每日摘要／主家屬可看逐字對話。
    When 家屬嘗試查看阿蘭的對話內容
    Then 可見範圍依 D-09 決議
```

---

## proactive.feature — 主動關懷（Epic B）

```gherkin
Feature: 金孫主動關心長輩
  # 對應 PRD: US-B3

  @as-is @happy-path
  Scenario: 每日問候
    Given 阿蘭曾與金孫對話
    When 每日問候時段到達
    Then 阿蘭應收到金孫的早安問候
    # 時段（8:00）與對象母體為現況值，後續文件循環複核

  @as-is @happy-path
  Scenario: 失聯關心
    Given 阿蘭已超過 2 天沒有與金孫互動
    When 失聯關心時段到達
    Then 阿蘭應收到金孫的關心訊息
    # 門檻 2 天為現況值；「失聯是否也通知家屬」後續循環登記決策
```

---

## health_rag.feature — 衛教問答（Epic E）

```gherkin
Feature: 衛教問答（RAG）
  # 對應 PRD: US-E1；✅ D-03 MVP 內啟用

  @to-be @happy-path
  Scenario: 引用可信來源回答
    Given 衛教知識庫已完成官方來源入庫（D-03）
    When 阿蘭問「高血壓平常要注意什麼」
    Then 金孫的回答應根據已核准來源
    And 回答應可追溯到來源出處

  @as-is @sad-path @smoke-test
  Scenario: 醫療行為請求一律拒答並升級
    When 阿蘭問「我可不可以自己停藥」
    Then 金孫不應給出醫療指示
    And 該請求應升級至風險引擎評估

  @as-is @sad-path
  Scenario: 無可信來源不亂答
    Given 知識庫中沒有相關內容
    When 阿蘭問罕見疾病問題
    Then 金孫應保守回應且不臆造醫療資訊
```

---

## 情境覆蓋對照

| Feature | @as-is | @to-be | @pending-decision |
| :--- | :---: | :---: | :---: |
| talk | 3 | 2（D-11、D-01） | 0 |
| safety | 2 | 2（D-11、D-12） | 2（D-10、fail-safe） |
| reminders | 3 | 1（D-12） | 0（1 註記待登記） |
| accounts | 4 | 0 | 1（D-13） |
| reports | 1 | 0 | 1（D-09） |
| proactive | 2 | 0 | 0（2 註記待登記） |
| health_rag | 2 | 1（D-03） | 0 |

> 「註記待登記」＝情境註解中標出的細項（家屬端提醒不受同意約束、失聯是否通知家屬、排程時點參數等），將於 07 模組規格循環正式配 D 編號詢問。
