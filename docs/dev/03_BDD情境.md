# BDD 情境 - 金孫 KinSun

> **版本:** v1.1 | **更新:** 2026-07-09 | **狀態:** ✅ 定稿（會議決議已回填；⚠ D-72 三級制於己-4 施工後全檔 L2/L3 用語同步改寫）
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

  @as-is @happy-path
  Scenario: 打字與語音同等對待（✅ D-11，甲-4 已完成 2026-07-09）
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
  Scenario: 絕對危急詞觸發頂級警訊
    # ⚠ D-72（2026-07-09）：分級改三級刪 L3——as-is 記 L3，己-4 施工後改記 L2（頂級）
    When 阿蘭說「救命」
    Then 應記錄一筆頂級危急事件（as-is L3 → to-be L2）
    And 家屬應收到含「撥打 119」提示的通知
    And 通知應先於回覆生成（回覆失敗也不影響通知）

  @as-is
  Scenario: 症狀詞觸發 L2
    When 阿蘭說「我今天有點頭暈」
    Then 應記錄一筆 L2 危急事件
    And 家屬應收到關懷提醒通知

  @as-is
  Scenario: 重複警訊重複通知（✅ D-10 定案維持現狀，會-5）
    Given 阿蘭在十分鐘內連續三次提到「跌倒」
    When 危急偵測連續觸發
    Then 每次都應通知全部家屬（不做冷靜期、不去重、不逐級升級）

  @to-be
  Scenario: L1 小訊號進每日摘要（✅ D-10 會-5，己-5）
    When 阿蘭說「最近都睡不好」且被判為 L1
    Then 不應即時通知家屬
    And 當日的每日摘要應提及此小訊號

  @as-is
  Scenario: 打字求救進安全網（✅ D-11，甲-4 已完成 2026-07-09）
    When 阿蘭打字「我想不開」
    Then 應與語音同等分級並記錄危急事件
    And 家屬應照常收到通知

  @to-be
  Scenario: 純 App 家屬收到警報（✅ D-12）
    Given 家屬只使用 App、未綁定 LINE
    When 阿蘭觸發 L2 以上危急事件
    Then 家屬開啟 App 應能看到該警報
    # 真推播於階段 5（D-08）後補：不開 App 也能收到

  @to-be @sad-path
  Scenario: LLM 分級器故障時的安全網（✅ D-31，甲-5）
    Given 危急分級 LLM 服務故障
    When 阿蘭說出不含關鍵詞的非空語句
    Then 該句應保守記為 L1 留痕（不通知家屬、事後可回查）
    And 失敗率超過門檻時應觸發維運告警
```

---

## reminders.feature — 用藥與回診提醒（Epic C）

```gherkin
Feature: 用藥與回診提醒
  # 對應 PRD: US-C1, US-C2

  @as-is @happy-path
  Scenario: 用藥時段提醒
    Given 家屬已為阿蘭設定早上時段的血壓藥
    When 早上提醒時段到達
    Then 阿蘭應收到含藥名的提醒訊息

  @to-be @sad-path
  Scenario: 提醒不查同意（✅ D-30 會-1，己-1）
    # as-is：用藥提醒會查同意、未同意不發——決議統一為「不查」，此檢查將移除
    Given 阿蘭的知情同意狀態為任意值
    When 任一用藥提醒時段到達
    Then 阿蘭仍應收到提醒（出站訊息不受同意狀態影響）

  @as-is @happy-path
  Scenario: 回診雙窗提醒
    Given 阿蘭明天有回診「心臟科」
    When 回診提醒時段到達
    Then 阿蘭應收到回診提醒
    And 全部家屬也應收到回診提醒
    # ✅ D-30（會-1）：提醒一律不查同意——長輩端與家屬端標準已統一

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

  # ✅ D-13（會-2）：不做撤回入口——長輩不想用就自行停用／刪 App，本情境撤除。
  # revoke_consent 服務層死碼於己-8 清理時處置。
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

  @to-be @happy-path
  Scenario: 家屬查看每日摘要（✅ D-09 會-4，己-3）
    Given 阿蘭昨日與金孫有對話且系統已生成摘要
    When 家屬開啟阿蘭的每日摘要
    Then 應看到當日摘要內容（含 L1 小訊號——己-5）

  @as-is @sad-path
  Scenario: 家屬不可看逐字對話（✅ D-09 會-4）
    When 家屬嘗試查看阿蘭的逐字對話內容
    Then 系統不應提供逐字對話（僅管理員後台可見，供調適／測試）
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
| safety | 3 | 4（D-11、D-12、D-10 L1 摘要、D-31） | 0 |
| reminders | 2 | 2（D-12、D-30 不查同意） | 0 |
| accounts | 4 | 0 | 0（D-13 決議不做，情境撤除） |
| reports | 1 | 1（D-09 摘要） | 0（另 1 as-is 邊界情境） |
| proactive | 2 | 0 | 0 |
| health_rag | 2 | 1（D-03） | 0 |

> 2026-07-09 會議決議回填：@pending-decision 全數清零（D-10／13／09／30／31 已定案改寫；fail-safe 併 D-31）。⚠ D-72 三級制的用語（L3→L2）於己-4 施工時全檔同步。
