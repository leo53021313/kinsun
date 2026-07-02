# 家屬端 LIFF 用藥 CRUD 設計（B2 第一切片）

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：① 家屬端（LIFF 儀表板）、② 後端服務／API、⑥ 用藥提醒。
> 前置：[家屬端 LIFF 入口 B1](2026-06-30-家屬端LIFF入口B1-design.md)（驗證 + REST 骨架 + 長輩清單）、[用藥提醒](2026-06-29-用藥提醒-design.md)（`MedicationService`）。
> 本案是 B2「管理表單上 LIFF」拆解後的**第一個垂直切片**：用藥 CRUD。後續切片：回診 CRUD、帳號（建檔 + 邀請家屬）。

---

## 1. 背景與目標

B1 已打通 LIFF 驗證 + REST 骨架 + 唯讀長輩清單。本案讓家屬在 LIFF 網頁**管理某長輩的用藥**（查看／新增／編輯／刪除），呼叫新的 REST CRUD 端點；既有 LINE 文字流（用藥選單）保留為另一條入口、不動。

**完成後：** 家屬在 LIFF 清單點某長輩 → 進入該長輩用藥頁 → 可查看、用表單新增、編輯、刪除用藥；所有寫入經授權檢查（只能動自己管理的長輩）。

**本案新增的關鍵安全要求：** B1 端點 `/api/me/elders` 由登入者 userId 自推、天生安全；B2 端點帶 `elder_id`，故每次讀寫都須驗證「登入家屬確實管理該 elder」，並驗證 `med_id` 屬於該 elder，防止以 id 探測/竄改他人資料（IDOR）。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* 後端：`web/api.py` 的 `create_api_router` 擴充用藥四端點 + 共用授權 helper；`MedicationService.update`。
* 前端：`frontend/` 導入 `react-router-dom`，B1 單頁重構為路由化；新增用藥頁（清單 + 新增/編輯表單 + 刪除）。
* `app.py` 把 `medications` 傳入 `create_api_router`。
* 後端離線測試（`test_api_medications.py`）；`test_api_elders.py` 補參數；前端 typecheck + build。

### 2.2 不在範圍內（後續切片）
* 回診 CRUD、帳號（建檔 + 邀請家屬）on LIFF。
* 報告（D/E）。
* 用藥提醒鐘點/吃藥確認等行為改動（沿用既有）。
* React 單元測試框架、樂觀更新、分頁。

---

## 3. 後端 REST 端點（web/api.py）

`create_api_router(*, verifier: LiffVerifier, accounts: AccountService, medications: MedicationService) -> APIRouter`。沿用 B1 的 `current_guardian` dependency（回 LINE userId）。新增閉包 helper：

* `_assert_manages(line_user_id, elder_id)`：`elder_id` 不在 `{e.elder_id for e in accounts.elders_managed_by(line_user_id)}` → `HTTPException(404)`。
* `_assert_med_under_elder(elder_id, med_id)`：`med_id` 不在 `{m.med_id for m in medications.list_for_elder(elder_id)}` → `HTTPException(404)`。
* `_parse_slots(raw: list[str]) -> tuple[MedicationSlot, ...]`：每項轉 `MedicationSlot`（非法 → 400）；空 → 400；依 `SLOT_ORDER` 正規化、去重。

請求 body（Pydantic，FastAPI 內建，非新套件）：
```python
class MedicationIn(BaseModel):
    name: str
    slots: list[str]
```

| 方法 端點 | 行為 | 守門 | 回應 |
|---|---|---|---|
| `GET /api/elders/{elder_id}/medications` | 列用藥 | `_assert_manages` | 200 `{"medications":[<med>]}` |
| `POST /api/elders/{elder_id}/medications` | 新增 | `_assert_manages` + 驗 name/slots | 201 `<med>` |
| `PUT /api/elders/{elder_id}/medications/{med_id}` | 編輯 | `_assert_manages` + `_assert_med_under_elder` + 驗 name/slots | 200 `<med>` |
| `DELETE /api/elders/{elder_id}/medications/{med_id}` | 刪除 | `_assert_manages` + `_assert_med_under_elder` | 204 |

* `<med>` = `{"med_id": str, "name": str, "slots": ["morning"|...]}`。
* `name.strip()` 空 → 400。
* 授權/存在性失敗一律 **404**（不洩漏 elder/med 是否存在）；未帶/無效 token → 401（沿用 B1 `current_guardian`）。

`MedicationService.update`：
```python
def update(self, med_id: str, elder_id: str, name: str, slots: tuple[MedicationSlot, ...]) -> Medication:
    med = Medication(med_id, elder_id, name, tuple(slots))
    self._store.add(med)  # 以 med_id upsert（store.add 本即 upsert）
    return med
```

---

## 4. 前端（frontend/，react-router）

新增依賴 `react-router-dom`。B1 單頁重構為路由化：

```
frontend/src/
  main.tsx              掛 <App/>
  App.tsx               LIFF 登入 gate（liff.init 一次）→ <BrowserRouter basename="/liff"> + <Routes>
  api.ts                apiFetch（自動帶 Bearer ID token；401 處理）+ 各 API 函式
  meds.ts               slot 值↔中文標籤（morning→早上、noon→中午、evening→晚上、bedtime→睡前）+ 順序
  pages/EldersPage.tsx       長輩清單（複用 B1），每筆 <Link> 到 /elders/:id/medications
  pages/MedicationsPage.tsx  某長輩用藥：清單 + 新增/編輯表單 + 刪除
```

* **`App.tsx`（auth gate）**：`await liff.init({liffId})` → `!isLoggedIn` → `liff.login()` → 登入後渲染 `<BrowserRouter basename="/liff">`。
* **`api.ts`**：`apiFetch(path, init)` 每次以 `liff.getIDToken()` 帶 `Authorization: Bearer <token>`；非 2xx 拋錯（401 提示重新登入）。匯出 `listElders`、`listMedications`、`addMedication`、`updateMedication`、`deleteMedication`。
* **路由**：`basename="/liff"` 對齊 Vite `base:"/liff/"`。`/` → `EldersPage`；`/elders/:elderId/medications` → `MedicationsPage`。
* **`MedicationsPage`**：載入清單；新增表單＝藥名 input + 四時段 checkbox；每筆「編輯」（帶入表單→PUT）、「刪除」（DELETE）；送出後重抓清單；錯誤顯示友善訊息（不白屏）。表單邏輯內含於頁面（YAGNI，不另抽元件）。

---

## 5. 接線（app.py）

`create_api_router` 改傳三參數（`medications` 已於組裝層建好）：
```python
app.include_router(create_api_router(verifier=verifier, accounts=accounts, medications=medications))
```
其餘不變。

---

## 6. 測試策略

**後端（離線、TestClient + fake）** `tests/test_api_medications.py`：
* `AccountService(FakeAccountRepository)` 建家屬 `U-son` 管理 `阿公`；`MedicationService(FakeMedicationStore)`；`_FakeVerifier`。
* 案例：
  * `GET` 管理中的長輩 → 200 + 清單；
  * `GET` 未管理的 elder（verifier 回他人 userId）→ 404；
  * `POST` 合法 → 201、清單出現；`name` 空 → 400；`slots` 空/非法 → 400；
  * `PUT` 改名/時段 → 200、清單反映；`med_id` 不屬該 elder → 404；
  * `DELETE` → 204、清單移除；`med_id` 不屬該 elder → 404；
  * 任一端點無 token → 401。
* `tests/test_api_elders.py`：補傳 `medications=`（`MedicationService(FakeMedicationStore())`），維持綠。

**前端**：`npm run typecheck` + `npm run build`（CI frontend job 已涵蓋）+ LINE 內人工驗證。沿用 B1，不引入 React 測試框架。

---

## 7. 錯誤處理（fail-safe）

* 授權/存在性失敗 → 404（不洩漏存在性）；輸入錯 → 400；無/失效 token → 401。
* 後端 DB 例外 → 500（REST 標準；不影響 webhook 對話主流程）。
* 前端：401 → 提示重新登入；其他非 2xx → 友善錯誤訊息。

---

## 8. 已定決策（列出供否決）

* 切片＝用藥 CRUD（含編輯 PUT）；回診/帳號為後續切片。
* 端點巢狀於 `/api/elders/{elder_id}/medications`；授權＝驗管理 + 驗 med 屬此 elder，失敗回 404。
* 端點擴充進既有 `create_api_router`（單檔），日後切片變大再拆。
* 前端導入 `react-router-dom`，B1 單頁重構為路由化（`/` 清單、`/elders/:id/medications` 用藥頁）。
* 輸入用 Pydantic body 模型 + 手動 slot 驗證；回應為精簡 JSON。
* 既有 LINE 文字流（用藥選單）保留不動。
