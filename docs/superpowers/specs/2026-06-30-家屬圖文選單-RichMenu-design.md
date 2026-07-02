# 家屬圖文選單（Rich Menu 開 LIFF）設計

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：① 家屬端（Rich Menu 圖文選單入口 → LIFF 儀表板）。
> 前置：[家屬端 LIFF 入口 B1](2026-06-30-家屬端LIFF入口B1-design.md)（LIFF 儀表板）、[帳號綁定流程](2026-06-29-帳號綁定流程-design.md)（`BindingFlow`）。

---

## 1. 背景與目標

LIFF 家屬儀表板（B1/B2/E1）已可用，但家屬每次要自己找入口。本案加上 **Rich Menu 圖文選單**：家屬在 LINE 聊天視窗底部有一個「開啟家屬儀表板」按鈕，一鍵開 LIFF。

選單**只給已綁定家屬**：佈建一個開啟 LIFF 的 Rich Menu（一次性），家屬綁定時把選單 link 給該使用者（長輩不受影響）。

**完成後：** 操作者跑一次佈建腳本建立 Rich Menu、取得 `rich_menu_id`；設為環境變數後，家屬一綁定（建立長輩或兌換家屬邀請碼）即自動獲得該選單，點按開啟 LIFF。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* `src/kinsun/channels/line/richmenu.py`：`build_rich_menu_request(liff_id)`、`setup_rich_menu(access_token, liff_id, image_path)`、CLI `main`。
* `LineApiMessenger` + `LineMessenger` Protocol 加 `link_rich_menu(user_id, rich_menu_id)`。
* `BindingFlow` 加 `on_guardian_bound` hook（成為家屬時 fail-safe link）。
* `app.py`：把 callback 接成「link 選單」；`config.py`：`rich_menu_id`；`.env.example`：`LIFF_ID`、`RICH_MENU_ID`。
* 測試：`test_richmenu.py`（payload 建構）、`test_binding_flow.py`（hook 觸發/fail-safe）。README 補佈建說明。

### 2.2 不在範圍內（後續）
* 多按鈕/多區塊選單、選單內其他功能（設定/報告快捷）。
* 預設選單（給所有人）、選單圖片產生/設計。
* 解除綁定時 unlink 選單。

---

## 3. 佈建模組（channels/line/richmenu.py）

用既有 `linebot.v3.messaging`（無新依賴）：
```python
def build_rich_menu_request(liff_id: str) -> RichMenuRequest:
    # RichMenuRequest(
    #   size=RichMenuSize(width=2500, height=843), selected=True,
    #   name="家屬選單", chat_bar_text="家屬選單",
    #   areas=[RichMenuArea(
    #     bounds=RichMenuBounds(x=0, y=0, width=2500, height=843),
    #     action=URIAction(uri=f"https://liff.line.me/{liff_id}", label="開啟家屬儀表板"))])

def setup_rich_menu(access_token: str, liff_id: str, image_path: str) -> str:
    # MessagingApi.create_rich_menu(build_rich_menu_request(liff_id)) → rich_menu_id
    # MessagingApiBlob.set_rich_menu_image(rich_menu_id, body=<image bytes>)
    # 回 rich_menu_id（不 set_default_rich_menu → 改用 link-per-user）

def main(argv=None) -> int:
    # 讀 env LINE_CHANNEL_ACCESS_TOKEN、LIFF_ID；argv[0]=圖片路徑
    # 印 rich_menu_id + 提示設為 RICH_MENU_ID
```

* 單一整條按鈕（2500×843）→ 開 LIFF（`https://liff.line.me/{liff_id}`）。
* 佈建腳本**只讀所需 env**（不走 `load_settings`，避免佈建也要備齊 DB/Gemini 金鑰）。
* 圖片規格：2500×843（或 2500×1686）、≤1MB、png/jpeg；操作者自備，對真 LINE 手動驗。
* **可測**：`build_rich_menu_request` → 斷言 `areas[0].action.uri`、size、單一 area、`chat_bar_text`。`setup_rich_menu`/`main` 為 I/O、不單元測。

---

## 4. 綁定時 link 選單

**`LineApiMessenger.link_rich_menu(user_id, rich_menu_id)`**（Protocol + 實作 `MessagingApi.link_rich_menu_id_to_user`）。

**`BindingFlow` hook**：
* `__init__` 多收 keyword-only `on_guardian_bound: Callable[[str], None] | None = None`（預設 None → 既有測試不受影響）。
* 私有 `_guardian_bound(line)`：`on_guardian_bound` 非 None 才呼叫，包 try/except（link 失敗只 log、不中斷綁定；沿用既有 logger）。
* 觸發兩點：
  * `_create_elder`：`create_elder` 之後 → `_guardian_bound(line)`（建立者＝主家屬）。
  * `_confirm` 家屬分支：`redeem_invite` 成功且 `role == GUARDIAN` → `_guardian_bound(line)`。
* 長輩綁定（role ELDER）**不**觸發。

---

## 5. 接線與設定（app.py、config.py）

* `config.py`：`Settings.rich_menu_id: str`；`load_settings` `rich_menu_id=env.get("RICH_MENU_ID", "")`。
* `app.py`：
  ```python
  rid = settings.rich_menu_id
  on_guardian_bound = (lambda line: messenger.link_rich_menu(line, rid)) if rid else None
  binding = BindingFlow(..., on_guardian_bound=on_guardian_bound)
  ```
  `RICH_MENU_ID` 未設 → `on_guardian_bound=None` → 不 link（功能停用、綁定照常）。
* `.env.example` 加 `LIFF_ID=`（佈建用）、`RICH_MENU_ID=`（app 綁定 link 用）。

---

## 6. 測試策略

**`tests/test_richmenu.py`**（離線；用既有 linebot 依賴）：
* `build_rich_menu_request("1234-ab")` → `areas[0].action.uri == "https://liff.line.me/1234-ab"`、`size.width==2500`、`size.height==843`、`len(areas)==1`、`chat_bar_text=="家屬選單"`。

**`tests/test_binding_flow.py`**（`_build_flow`/`_flow` 加可選 `on_guardian_bound` spy）：
* 建立長輩（flow 1）→ spy 被呼叫、參數為建立者 line；
* 兌換家屬邀請碼成功 → spy 被呼叫；
* 長輩兌換（ELDER）→ spy **不**被呼叫；
* callback 拋例外時綁定仍回成功訊息（fail-safe）。

`link_rich_menu`/`setup_rich_menu`/`main` 為 I/O、不單元測（沿用 messenger 慣例）。

---

## 7. 錯誤處理（fail-safe）

* `_guardian_bound` 包 try/except：link 選單失敗只 log、綁定照常完成。
* `RICH_MENU_ID` 未設 → 停用 link、不報錯。
* 佈建腳本對真 LINE 失敗 → 由 SDK 拋例外、操作者可見（一次性運維）。

---

## 8. 已定決策（列出供否決）

* 選單只給已綁定家屬（link-per-user），不設預設選單。
* 綁定成為家屬的兩點觸發 link：建立長輩（主家屬）、兌換家屬邀請碼。
* 單一整條按鈕（2500×843）→ 開 LIFF；圖片操作者自備（腳本吃路徑）。
* `rich_menu_id` 由佈建腳本印出、以 `RICH_MENU_ID` env 提供給 app。
* hook 用 `on_guardian_bound` callback，BindingFlow 不知 LINE/選單細節。
* 佈建與 link 屬 I/O、手動驗；單元測只涵蓋 payload 建構與 hook 觸發。
