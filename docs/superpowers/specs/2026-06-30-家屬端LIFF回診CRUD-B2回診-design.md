# 家屬端 LIFF 回診 CRUD 設計（B2 第二切片）

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：① 家屬端（LIFF 儀表板）、② 後端服務／API、⑥ 回診提醒。
> 前置：[家屬端 LIFF 入口 B1](2026-06-30-家屬端LIFF入口B1-design.md)、[用藥 CRUD B2](2026-06-30-家屬端LIFF用藥CRUD-B2用藥-design.md)（本案的鏡像範本）、[回診提醒](2026-06-30-回診提醒-design.md)（`AppointmentService`）。
> 本案是 B2 的第二垂直切片：回診 CRUD。為用藥切片的孿生，差異只在日期。

---

## 1. 背景與目標

用藥 CRUD（B2 第一切片）已上線。本案讓家屬在 LIFF 管理某長輩的回診（查看／新增／編輯／刪除），呼叫新的 REST CRUD 端點；既有 LINE 文字流（回診選單）保留不動。

**完成後：** 家屬在 LIFF 長輩清單點某長輩 → 進入該長輩回診頁 → 查看、用表單新增（日期 + 標籤）、編輯、刪除；所有讀寫經授權檢查（只能動自己管理的長輩、且 appt 屬該 elder）。

與用藥切片的唯一實質差異：用「日期」取代「時段」，且 API 驗證日期格式（`YYYY-MM-DD`）並拒絕過去日期（需注入時鐘）。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* 後端：`web/api.py` 的 `create_api_router` 加 `appointments` 與 `clock` 參數 + 回診四端點 + `assert_appt_under_elder` + 日期驗證 helper；`AppointmentService.update`。
* 前端：新增 `pages/AppointmentsPage.tsx`、`api.ts` 加回診函式、`EldersPage` 每長輩雙入口（用藥/回診）、`App.tsx` 加回診路由。
* `app.py` 把 `appointments` 與 `clock` 傳入 `create_api_router`。
* 後端離線測試（`test_api_appointments.py`）；`test_api_elders.py`、`test_api_medications.py` 補參數；前端 typecheck + build。

### 2.2 不在範圍內（後續切片）
* 帳號（建檔 + 邀請家屬）on LIFF。
* 報告（D/E）、Rich Menu。
* 回診提醒鐘點/通知行為改動（沿用既有）。
* 拆分 per-resource router（沿用「擴充單一 router、日後再拆」；待帳號切片檔案過大時處理）。

---

## 3. 後端 REST 端點（web/api.py）

`create_api_router(*, verifier, accounts, medications, appointments: AppointmentService, clock: Callable[[], datetime]) -> APIRouter`。沿用 `current_guardian`、`assert_manages`。

請求 body（Pydantic）：
```python
class AppointmentIn(BaseModel):
    date: str
    label: str
```

| 方法 端點 | 行為 | 守門/驗證 | 回應 |
|---|---|---|---|
| `GET /api/elders/{elder_id}/appointments` | 列回診（`list_for_elder`，依日期排序、含過去） | `assert_manages` | 200 `{"appointments":[<appt>]}` |
| `POST /api/elders/{elder_id}/appointments` | 新增 | `assert_manages` + 驗日期 + 驗 label | 201 `<appt>` |
| `PUT /api/elders/{elder_id}/appointments/{appt_id}` | 編輯 | `assert_manages` + `assert_appt_under_elder` + 驗日期/label | 200 `<appt>` |
| `DELETE /api/elders/{elder_id}/appointments/{appt_id}` | 刪除 | `assert_manages` + `assert_appt_under_elder` | 204 |

* `<appt>` = `{"appt_id": str, "date": str, "label": str}`。
* `assert_appt_under_elder(elder_id, appt_id)`：`appt_id` 不在 `{a.appt_id for a in appointments.list_for_elder(elder_id)}` → 404。
* 日期驗證 helper：
  ```python
  def parse_appt_date(raw: str) -> str:
      try:
          parsed = datetime.strptime(raw.strip(), "%Y-%m-%d").date()
      except ValueError:
          raise HTTPException(status_code=400, detail="invalid date")
      if parsed < clock().date():
          raise HTTPException(status_code=400, detail="date in past")
      return parsed.isoformat()
  ```
* `label.strip()` 空 → 400。
* 授權/存在性失敗一律 404；輸入錯 400；無/失效 token 401。

`AppointmentService.update`：
```python
def update(self, appt_id: str, elder_id: str, date: str, label: str) -> Appointment:
    appt = Appointment(appt_id, elder_id, date, label)
    self._store.add(appt)  # 以 appt_id upsert
    return appt
```

---

## 4. 前端（frontend/）

```
frontend/src/
  api.ts                     加 type Appointment + listAppointments/add/update/delete
  pages/AppointmentsPage.tsx 某長輩回診：清單 + 新增/編輯表單 + 刪除
  pages/EldersPage.tsx       每長輩雙入口連結（用藥 / 回診）
  App.tsx                    加 /elders/:elderId/appointments 路由
```

* **`api.ts`**：`type Appointment = { appt_id: string; date: string; label: string }`；`listAppointments(elderId)`、`addAppointment(elderId, date, label)`、`updateAppointment(elderId, apptId, date, label)`、`deleteAppointment(elderId, apptId)`（沿用 `apiFetch`）。
* **`AppointmentsPage`**（鏡像 `MedicationsPage`）：載入清單；新增表單＝`<input type="date" min={今天}>` + 標籤 `<input type="text">`；每筆「編輯」「刪除」；送出後重抓；錯誤友善訊息。`今天 = new Date().toISOString().slice(0, 10)`（僅前端體驗用，把關在後端）。
* **`EldersPage`**：每長輩列兩個 `<Link>`：「用藥」→ `/elders/:id/medications`、「回診」→ `/elders/:id/appointments`。
* **`App.tsx`**：加 `<Route path="/elders/:elderId/appointments" element={<AppointmentsPage />} />`。

---

## 5. 接線（app.py）

`appointments` 已於回診提醒切片建好、`tz` 既有：
```python
app.include_router(create_api_router(
    verifier=verifier, accounts=accounts, medications=medications,
    appointments=appointments, clock=lambda: datetime.now(tz),
))
```

---

## 6. 測試策略

**後端（離線、TestClient + fake + 固定 clock）** `tests/test_api_appointments.py`：
* `AccountService(FakeAccountRepository)` 建家屬 `U-son` 管理 `阿公`；`AppointmentService(FakeAppointmentStore)`；`_FakeVerifier`；`clock=lambda: NOW`（`NOW=2026-07-10`）。
* 案例：
  * `GET` 未管理 elder → 404；
  * `POST` 未來日期合法 → 201、清單出現；過去日期（`2026-07-01`）→ 400；格式錯（`abc`）→ 400；`label` 空 → 400；
  * `PUT` 改日期/標籤 → 200、清單反映；`appt_id` 不屬該 elder → 404；
  * `DELETE` → 204、清單移除；不屬 → 404；
  * 無 token → 401。
* `tests/test_api_medications.py`、`tests/test_api_elders.py`：`create_api_router(...)` 補 `appointments=AppointmentService(FakeAppointmentStore())`、`clock=lambda: NOW`，維持綠。

**前端**：`npm run typecheck` + `build`（CI frontend job 涵蓋）+ LINE 內人工驗證。

---

## 7. 錯誤處理（fail-safe）

* 授權/存在性失敗 → 404；輸入錯（日期格式/過去/空標籤）→ 400；無/失效 token → 401。
* 後端 DB 例外 → 500（不影響 webhook 對話主流程）。
* 前端：401 → 提示重新登入；其他非 2xx → 友善錯誤訊息。

---

## 8. 已定決策（列出供否決）

* 切片＝回診 CRUD（含編輯 PUT）；為用藥切片的鏡像。
* 端點巢狀於 `/api/elders/{elder_id}/appointments`；授權＝驗管理 + 驗 appt 屬此 elder，失敗 404。
* 日期 API 驗格式 + 拒過去（注入 `clock`）；前端用 `<input type="date" min>` 輔助。
* 列表回 `list_for_elder`（全部、依日期排序），與用藥對稱。
* 沿用擴充單一 `create_api_router`（日後再拆）。
* `EldersPage` 每長輩提供用藥/回診雙入口。
* 既有 LINE 文字流（回診選單）保留不動。
