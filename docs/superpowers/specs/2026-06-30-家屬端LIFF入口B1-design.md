# 家屬端 LIFF 入口 B1 設計（身分驗證 + REST 骨架 + 端到端薄切片）

> 對應架構圖 [長輩看護系統架構-分層版.drawio](../../長輩看護系統架構-分層版.drawio)：① 家屬端（LIFF 儀表板）、② 後端服務／API。
> 本案是「完整 LIFF 儀表板」拆解後的**第一個子專案（地基）**。後續子專案：B2 管理表單上 LIFF、D 報告資料收集、E 報告檢視、Rich Menu 開 LIFF —— 皆依賴本案的 REST + 驗證骨架。
> 前置：[帳號綁定核心](2026-06-29-帳號綁定核心-design.md)（`AccountService.elders_managed_by`）。

---

## 1. 背景與目標

家屬目前只能在 LINE 用文字選單「設定」操作，沒有任何網頁儀表板。團隊決定走**完整 LIFF 網頁**路線（而非留在 LINE 內）。這是專案**首次引入對外 REST API 與前端網頁**，屬架構層級新增，故先做一個**端到端薄切片**驗證新架構可行，再堆後續 CRUD／報告。

**完成後：** 家屬在 LINE 開啟 LIFF → 自動以 LINE 身分登入 → 後端驗證 → 網頁顯示「您管理的長輩清單」。打通 `LIFF 前端 → 帶 ID token 的 REST API → 驗證 → DB → 渲染` 全鏈路。

**非目標（後續子專案）：** 任何 CRUD（建檔／用藥／回診／邀請家屬表單）、報告、Rich Menu。本案只有一個唯讀端點與一頁清單。

---

## 2. 範圍（Scope）

### 2.1 在範圍內
* 後端 `src/kinsun/web/` 套件：`auth.py`（`LiffVerifier` Protocol + `LineIdTokenVerifier`）、`api.py`（`create_api_router`：`GET /api/me/elders` + 驗證 dependency）。
* [`app.py`](../../../src/kinsun/app.py) 組裝層接線：掛 API router + 條件式掛載 `/liff` 靜態檔。webhook 不動。
* [`config.py`](../../../src/kinsun/config.py)：`liff_channel_id`、`liff_timeout_seconds`。
* 前端 `frontend/`：React + Vite + TypeScript 單頁，LIFF 登入 → 取 ID token → 呼叫 API → 顯示長輩清單。
* 後端測試（離線）；前端 typecheck + build 把關。
* CI 新增 frontend job；`.gitignore`、`.env.example`、README 同步。

### 2.2 不在範圍內（後續）
* 任何寫入／CRUD 端點與表單（B2）。
* 報告與其資料收集（D、E）。
* Rich Menu 開 LIFF。
* 前端單元測試框架、SPA 多頁路由、權限細分（B1 僅「家屬看自己的長輩」）。
* CORS（同源供應，不需要）。

---

## 3. 身分驗證（src/kinsun/web/auth.py）

```python
class AuthError(Exception):
    """LIFF 身分驗證失敗。"""

class LiffVerifier(Protocol):
    def verify(self, id_token: str) -> str: ...   # 回傳 LINE userId（sub）

class LineIdTokenVerifier:
    """POST id_token 到 LINE /oauth2/v2.1/verify，回傳 sub。urllib，無新依賴。"""
    def __init__(self, channel_id: str, timeout: float) -> None: ...
    def verify(self, id_token: str) -> str: ...
```

* 端點：`POST https://api.line.me/oauth2/v2.1/verify`，body `application/x-www-form-urlencoded`：`id_token=<token>&client_id=<channel_id>`。
* 成功回 JSON，取 `payload["sub"]`（LINE userId）。`sub` 非字串 → `AuthError`。
* `urllib.error.URLError`（含 `HTTPError` 400 無效 token）、`OSError`、`json.JSONDecodeError` → `AuthError`（沿用 `DgxAsrClient` 的 urllib 模式，無新第三方套件）。
* `channel_id` = **LINE Login channel ID**（承載 LIFF 者），須與 Messaging API bot **同 provider**，回傳 `sub` 才等於綁定時存的家屬 `line_user_id`。

---

## 4. REST API（src/kinsun/web/api.py）

```python
def create_api_router(*, verifier: LiffVerifier, accounts: AccountService) -> APIRouter:
    router = APIRouter(prefix="/api")

    def current_guardian(authorization: str = Header(default="")) -> str:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="missing bearer token")
        try:
            return verifier.verify(token)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail="invalid token") from exc

    @router.get("/me/elders")
    def my_elders(line_user_id: str = Depends(current_guardian)) -> dict:
        elders = accounts.elders_managed_by(line_user_id)
        return {"elders": [{"elder_id": e.elder_id, "name": e.name} for e in elders]}

    return router
```

* 驗證做成 FastAPI dependency；`verifier` 與 `accounts` 由工廠注入（測試可換 fake）。
* 回應形狀：`{"elders": [{"elder_id": str, "name": str}, ...]}`（空清單為合法回應）。
* 授權：家屬只看 `elders_managed_by(自己的 userId)`；不接受任意 `elder_id` 查詢（B1 無此端點）。

---

## 5. 組裝接線（app.py）

webhook 主流程不動；在組裝層加：
```python
app = create_app(...)                              # 既有
verifier = LineIdTokenVerifier(settings.liff_channel_id, settings.liff_timeout_seconds)
app.include_router(create_api_router(verifier=verifier, accounts=accounts))
dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if dist.is_dir():
    app.mount("/liff", StaticFiles(directory=dist, html=True), name="liff")
return app
```
* 路由：`/line/webhook`（既有）、`/api/me/elders`（新）、`/liff`（靜態 SPA）。同源 → 免 CORS。
* `pathlib`（OS-agnostic）；`parents[2]` = repo 根（`app.py` 在 `src/kinsun/`）。
* `dist` 不存在就不掛載，後端照常啟動（測試／純 webhook 開發不需 node build）。
* `build_app` 由 `return create_app(...)` 改為 `app = create_app(...)` → 接線 → `return app`。

---

## 6. 設定（config / .env）

`Settings` 新增（皆可選、不影響既有啟動）：

| 變數 | 預設 | 用途 |
|------|------|------|
| `LIFF_CHANNEL_ID` | `""` | LINE Login channel ID，驗 ID token 的 `client_id` |
| `LIFF_TIMEOUT_SECONDS` | `10` | 呼叫 verify 端點逾時（float） |

`load_settings`：`liff_channel_id=env.get("LIFF_CHANNEL_ID", "")`、`liff_timeout_seconds=float(env.get("LIFF_TIMEOUT_SECONDS", "10"))`。`.env.example` 同步。
（前端另需 `VITE_LIFF_ID`，屬前端 build 設定，見 §7。）

---

## 7. 前端（frontend/ React + Vite + TypeScript）

```
frontend/
  package.json        scripts: dev / build / preview / typecheck
  vite.config.ts      base: "/liff/"；server.proxy: { "/api": "http://localhost:8000" }
  tsconfig.json
  index.html
  .env.example        VITE_LIFF_ID=
  src/main.tsx
  src/App.tsx
```

* 依賴：`react`、`react-dom`、`@line/liff`；devDeps：`vite`、`@vitejs/plugin-react`、`typescript`、`@types/react`、`@types/react-dom`。
* `App.tsx` 流程：
  1. `await liff.init({ liffId: import.meta.env.VITE_LIFF_ID })`
  2. `if (!liff.isLoggedIn()) liff.login()`（導去 LINE 登入後返回）
  3. `const token = liff.getIDToken()`
  4. `fetch("/api/me/elders", { headers: { Authorization: \`Bearer ${token}\` } })`
  5. 200 → 顯示「您管理的長輩」清單；空清單 → 引導「請在 LINE 回覆『設定』建立長輩」；401 → 顯示「請重新登入」。
* `base: "/liff/"`：SPA 掛在 `/liff`，build 出的資產路徑需此前綴。
* API 用絕對路徑 `/api/...` 同源呼叫；dev 用 Vite proxy 轉本機後端。
* `VITE_LIFF_ID` 放 `frontend/.env`（不進版控）；`.env.example` 留範本。

---

## 8. 測試策略

**後端（離線、注入 fake）**
* `tests/test_web_auth.py`：monkeypatch `urllib.request.urlopen`——
  * 假回應 `{"sub": "U-x"}` → `verify` 回 `"U-x"`；
  * 回應缺 `sub` → `AuthError`；
  * `urlopen` 拋 `URLError` → `AuthError`。
* `tests/test_api_elders.py`：`TestClient`（同 `test_webhook.py`）+ `FakeVerifier`（回固定 userId）+ `AccountService(FakeAccountRepository)`——
  * `Authorization: Bearer x` → 200 + 該家屬長輩清單；
  * 無 header / 非 Bearer → 401；
  * `FakeVerifier` 拋 `AuthError` → 401；
  * 家屬無長輩 → 200 + `{"elders": []}`。

**前端**：`npm run typecheck`（tsc）+ `npm run build` 把關 + LINE 內人工驗證登入流程。B1 不引入 React 單元測試框架（YAGNI）。

---

## 9. 錯誤處理（fail-safe）

* 驗證失敗一律 401、不洩漏細節。
* web 層獨立於對話主流程；API／靜態掛載異常不影響 webhook。
* `frontend/dist` 不存在 → 不掛載 `/liff`，後端照常啟動。
* secret／channel id 走環境變數，不寫死。

---

## 10. CI / 部署 / 設定注意

* CI（`.github/workflows/ci.yml`）新增 `frontend` job 與 Python job 並列：`setup-node` → `npm ci` → `npm run typecheck` → `npm run build`（`working-directory: frontend`）。Python job 不變。
* `.gitignore` 加 `frontend/node_modules/`、`frontend/dist/`。
* 部署：正式環境先在 `frontend/` 跑 `npm run build` 產出 `dist`，後端才供應 `/liff`。
* LINE 設定：建一個與 Messaging API **同 provider** 的 **LINE Login channel** + LIFF app，endpoint 指向 `https://<host>/liff`；channel ID → `LIFF_CHANNEL_ID`，LIFF ID → 前端 `VITE_LIFF_ID`。
* README 補「家屬端 LIFF（開發／部署）」一節。

---

## 11. 已定決策（列出供否決）

* 走完整 LIFF 網頁路線（非留在 LINE 內）；本案只做地基薄切片。
* 前端：React + Vite + TypeScript，置於 `frontend/`，由 FastAPI 同源供應（免 CORS）。
* 驗證：前端送 LIFF **ID token**，後端 POST LINE verify 端點取 `sub`；無新後端依賴。
* Login channel 與 Messaging API 同 provider（userId 一致）為硬性前提。
* B1 唯一端點 `GET /api/me/elders`（唯讀）；唯一前端頁面為長輩清單。
* `dist` 不存在則後端不掛 `/liff`、照常啟動。
