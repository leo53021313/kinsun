# 家屬端 LIFF 建檔 + 邀請家屬設計（B2 第三切片）

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：① 家屬端（LIFF 儀表板）、② 後端服務／API、⑦ 帳號。
> 前置：[家屬端 LIFF 入口 B1](2026-06-30-家屬端LIFF入口B1-design.md)、[用藥 CRUD B2](2026-06-30-家屬端LIFF用藥CRUD-B2用藥-design.md)（REST/驗證範本）、[帳號綁定核心](2026-06-29-帳號綁定核心-design.md)（`AccountService.create_elder` / `generate_invite`）。
> 本案是 B2 的第三垂直切片：建檔 + 邀請家屬。

---

## 1. 背景與目標

用藥、回診 CRUD 已上線。本案讓家屬在 LIFF 網頁**建立長輩檔案**並**邀請其他家屬**，呼叫新的 REST 端點；既有 LINE 文字流（「設定」選單的建檔/邀請）保留不動。

**完成後：** 家屬在 LIFF 首頁可新增長輩（系統回傳「長輩綁定碼」交給長輩）、對每位長輩產生「家屬邀請碼」交給其他家屬。

**同意語意不變：** 兩個端點都只**產生邀請碼**；綁定與知情同意仍是長輩/家屬拿碼到 LINE 兌換時記錄（`consent_by=SELF`）。網頁端不替任何人代簽同意。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* 後端：`web/api.py` 加 `POST /api/elders`（建檔 + 自動產生長輩綁定碼）與 `POST /api/elders/{elder_id}/guardian-invites`（產生家屬邀請碼）。兩端點只用既有 `accounts`，`create_api_router` 簽章不變。
* 前端：`api.ts` 加 `createElder`、`generateGuardianInvite`；`EldersPage` 加新增長輩表單 + 每長輩邀請家屬按鈕 + 邀請碼顯示。
* 後端離線測試（`test_api_accounts.py`）；前端 typecheck + build。

### 2.2 不在範圍內（後續）
* 已綁定家屬清單檢視、家屬權限/升級順序管理。
* 撤銷同意、刪除長輩/家屬、編輯長輩姓名。
* 邀請碼 LINE 分享（shareTargetPicker）—— 先純文字顯示。
* 報告（D/E）、Rich Menu。

---

## 3. 後端 REST 端點（web/api.py）

沿用 `current_guardian`（回 LINE userId）、`assert_manages`。新增 Pydantic：
```python
class CreateElderIn(BaseModel):
    elder_name: str
    guardian_name: str = ""   # 前端帶 LIFF 暱稱；取不到則空字串
```

| 方法 端點 | 行為 | 守門/驗證 | 回應 |
|---|---|---|---|
| `POST /api/elders` | 建長輩 + 自動產生長輩綁定碼 | `current_guardian`（任何登入家屬可建）+ `elder_name` 非空 | 201 `{"elder_id","name","invite_code"}` |
| `POST /api/elders/{elder_id}/guardian-invites` | 產生家屬邀請碼 | `current_guardian` + `assert_manages` | 201 `{"invite_code"}` |

* 建檔：
  ```python
  name = body.elder_name.strip()
  if not name:
      raise HTTPException(status_code=400, detail="elder_name required")
  elder = accounts.create_elder(line_user_id, body.guardian_name, name)
  invite = accounts.generate_invite(elder.elder_id, InviteRole.ELDER)
  return {"elder_id": elder.elder_id, "name": elder.name, "invite_code": invite.code}
  ```
* 邀請家屬：
  ```python
  assert_manages(line_user_id, elder_id)
  invite = accounts.generate_invite(elder_id, InviteRole.GUARDIAN)
  return {"invite_code": invite.code}
  ```
* 有效期固定（既有 `INVITE_TTL_HOURS=24`）；回應不帶 `expires_at`，前端顯示靜態「24 小時內有效」。
* 授權失敗 404；輸入錯 400；無/失效 token 401。
* 不新增 `AccountService` 方法（`create_elder`、`generate_invite` 既有）。`InviteRole` 由 `kinsun.accounts.models` 匯入。

---

## 4. 前端（frontend/）

* **`api.ts`**：
  ```typescript
  export async function createElder(elderName, guardianName):
      Promise<{ elder_id: string; name: string; invite_code: string }>   // POST /api/elders
  export async function generateGuardianInvite(elderId):
      Promise<{ invite_code: string }>                                   // POST .../guardian-invites
  ```
* **`EldersPage`** 擴充（仍是首頁/長輩頁）：
  - 「新增長輩」表單：長輩稱呼 input → 送出時 `const p = await liff.getProfile()` 取暱稱 → `createElder(name, p.displayName)` → 顯示**長輩綁定碼**面板（「請交給長輩在 LINE 貼上完成綁定，24 小時內有效」）→ 重抓清單、清空表單。
  - 每位長輩列一個「邀請家屬」按鈕 → `generateGuardianInvite(elderId)` → 顯示**家屬邀請碼**面板（「請交給其他家屬在 LINE 貼上，24 小時內有效」）。
  - 既有用藥/回診雙入口連結保留。
  - 錯誤顯示友善訊息（不白屏）。
* `liff.getProfile()` 需 profile scope（LIFF 預設即有）。

---

## 5. 接線（app.py）

不需改：兩端點只用既有 `accounts`，`create_api_router` 簽章不變。

---

## 6. 測試策略

**後端（離線、TestClient + fake）** `tests/test_api_accounts.py`：
* router 以 `create_api_router(verifier=_FakeVerifier(...), accounts=AccountService(FakeAccountRepository), medications=MedicationService(FakeMedicationStore()), appointments=AppointmentService(FakeAppointmentStore()), clock=lambda: NOW)` 建。
* 案例：
  * `POST /api/elders`（auth + `{elder_name:"阿公", guardian_name:"兒子"}`）→ 201、回 `invite_code`；該長輩出現在 `accounts.elders_managed_by("U-son")`；`accounts.preview_invite(code).role == InviteRole.ELDER`；
  * `elder_name` 空白 → 400；無 token → 401；
  * `POST /api/elders/{elder_id}/guardian-invites`（管理中）→ 201、`accounts.preview_invite(code).role == InviteRole.GUARDIAN`；
  * 對未管理的 elder 產家屬碼 → 404；無 token → 401。
* （此測試需在外部建立一位由 `U-son` 管理的長輩以測 guardian-invite；以 `accounts.create_elder("U-son", "兒子", "阿公")` 預備。）

**前端**：`npm run typecheck` + `build`（CI frontend job 涵蓋）+ LINE 內人工驗證。

---

## 7. 錯誤處理（fail-safe）

* 授權失敗 → 404；輸入錯（空 elder_name）→ 400；無/失效 token → 401。
* 後端 DB 例外 → 500（不影響 webhook 對話主流程）。
* 前端：401 → 提示重新登入；其他非 2xx → 友善錯誤訊息。

---

## 8. 已定決策（列出供否決）

* 切片＝建檔 + 邀請家屬；不含家屬清單檢視、權限/撤銷（後續）。
* `POST /api/elders` 一步建檔 + 自動產生長輩綁定碼。
* 主家屬姓名取自 LIFF `getProfile().displayName`（前端帶入 `guardian_name`）。
* 同意語意不變：網頁只產碼，兌換在 LINE 完成。
* 邀請碼純文字顯示 + 靜態「24 小時內有效」；不做 LINE 分享。
* 兩端點只用既有 `accounts`，不動 `create_api_router` 簽章、不加 `AccountService` 方法。
* 既有 LINE 文字流（建檔/邀請）保留不動。
