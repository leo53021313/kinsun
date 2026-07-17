# JS 端引入 linting 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `app/` 與 `frontend/` 都有可跑且全綠的 linter，且 CI 會擋——讓 JS 端有跟後端 ruff 對等的護欄。

**Architecture:** 兩套獨立設定（app 用 `eslint-config-expo` 因它懂 React Native 慣例，frontend 用 `typescript-eslint`），皆疊上 `eslint-plugin-react-hooks` v7 的 Compiler 層規則。先立設定讓違規現形（RED），再逐類修掉（GREEN），最後加 CI 步驟讓它真的有牙齒。

**Tech Stack:** eslint 9、typescript-eslint 8、eslint-plugin-react-hooks 7、eslint-config-expo 10、eslint-plugin-react-refresh

設計來源：`docs/superpowers/specs/2026-07-17-js端引入linting-design.md`。有疑義時以 spec 為準。

## Global Constraints

- 語言：台灣繁體中文，全形標點；程式碼註解、commit 訊息皆同。
- 分支：只在 `Leo` 上工作，不切 main、不自動 push。
- ⚠️ **不接受無註解的 `eslint-disable`**：每一個 disable 都必須附一行說明為什麼。
- ⚠️ **不可用 `if (error) setError(false)` 規避 set-state-in-effect**：條件式的同步 setState 仍是同步 setState，規則照樣抓，語意還更難懂。
- 版本以實測驗證過的為準：eslint 9.39.5、typescript-eslint 8.64.0、eslint-plugin-react-hooks 7.1.1。
- `app/` 的 `"lint": "expo lint"` script 維持不動——它本來就是對的，只是從來沒有設定檔可讀。
- 每個 Task 結束前工作區必須乾淨（`git status --short` 為空）。

---

### Task 1: `frontend/` 的 eslint 設定（讓違規現形）

**Files:**
- Create: `frontend/eslint.config.js`
- Modify: `frontend/package.json`（devDeps ＋ lint script）、`frontend/package-lock.json`

**Interfaces:**
- Consumes: 無
- Produces: `cd frontend && npm run lint` 這個指令（本 Task 結束時它會**紅**，共 8 個 error）

⚠️ 本 Task 刻意留下紅色的 lint——那是規則確實在抓東西的證據，也是 Task 2／3 的 RED。CI 步驟要到 Task 5 才加，所以這個中間狀態不會擋到任何人。

- [ ] **Step 1: 安裝依賴**

```bash
cd frontend && npm i -D eslint@9 typescript-eslint eslint-plugin-react-hooks eslint-plugin-react-refresh
```

- [ ] **Step 2: 加入 lint script**

在 `frontend/package.json` 的 `scripts` 中，於 `"typecheck": "tsc --noEmit"` 之後加入：

```json
    "lint": "eslint src"
```

- [ ] **Step 3: 建立設定檔**

建立 `frontend/eslint.config.js`：

```js
/**
 * frontend（LIFF ＋ 觀測後台）的 eslint 設定。
 *
 * 刻意不與 app/ 共用設定：app/ 是 React Native、frontend/ 是瀏覽器 Vite app，
 * 執行環境與慣例本就不同。實測顯示共用會製造假警報（通用設定看不懂 RN 載入
 * 資產的 require()），而假警報會訓練人忽略 linter。
 */

import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "dist-admin"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      // react-hooks v7 的 Compiler 層：除了經典的 rules-of-hooks／exhaustive-deps，
      // 另抓 set-state-in-effect（effect 裡同步 setState 會觸發連鎖重繪）與
      // refs（render 期間改 ref）。frontend 沒跑 React Compiler（React 18 ＋ Vite），
      // 但連鎖重繪在 React 18 一樣是真的效能問題，且與 app/ 同標準有其價值。
      ...reactHooks.configs.recommended.rules,
      // Vite HMR 要求元件檔只匯出元件，否則熱更新會整頁重載。
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
);
```

- [ ] **Step 4: 執行 lint，確認它抓到 8 個 error**

Run: `cd frontend && npm run lint`
Expected: FAIL — `✖ 8 problems (8 errors, 0 warnings)`，其中 7 個 `react-hooks/set-state-in-effect`（`SystemPage`、`ElderTimelinePage`、`TraceDetailPage`、`AccountTab`、`MemoryTab`、`RemindersTab`、`RiskNotificationsTab`）、1 個 `react-hooks/refs`（`usePolling.ts`）。

若數量或種類不符，**停下來回報**——代表 spec 的實測基準與現況已經漂移，不要硬改設定去湊。

- [ ] **Step 5: Commit**

```bash
cd /home/leo29/kinsun
git add frontend/package.json frontend/package-lock.json frontend/eslint.config.js
git commit -F - <<'EOF'
chore(frontend): 裝上 eslint，讓從未被檢查過的程式碼現形

frontend/ 從來沒有 linter——連 app/ 那種沒設定過的樣板 script 都沒有。本
commit 只做一件事：把尺立起來，讓既有違規現形。

⚠️ 本 commit 之後 npm run lint 是紅的（8 個 error）。這是刻意的：那是規則
確實在抓東西的證據，也是後續兩個 commit 的起點。CI 步驟要到最後才加，所以
這個中間狀態不會擋到任何人。

不與 app/ 共用設定，由實測否決：用通用 typescript-eslint 量 app/，載入音效
的 require() 被判錯——那是 React Native 的標準寫法。app/ 是 RN、frontend/
是瀏覽器 Vite app，共用只會製造假警報，而假警報會訓練人忽略 linter。

採 react-hooks v7 的 Compiler 層。frontend 沒跑 React Compiler（React 18
＋ Vite），但連鎖重繪在 React 18 一樣是真的效能問題，且與 app/ 同標準有其
價值。

IMPACT：
- 純工具設定，無執行期程式碼變更、無行為變更。
- npm run lint 暫時為紅；CI 尚未跑 lint，不影響任何人。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: 修 `usePolling` 的 render 期間改 ref

**Files:**
- Modify: `frontend/src/admin/usePolling.ts`

**Interfaces:**
- Consumes: Task 1 的 `npm run lint`
- Produces: 無介面變更（`usePolling(callback, intervalMs)` 簽章不動）

- [ ] **Step 1: 確認這條 error 存在（RED）**

Run: `cd frontend && npx eslint src/admin/usePolling.ts`
Expected: FAIL — `6:3 error ... Cannot update ref during render  react-hooks/refs`

- [ ] **Step 2: 修正**

在 `frontend/src/admin/usePolling.ts` 中，將：

```ts
export function usePolling(callback: () => void | Promise<void>, intervalMs: number): void {
  const saved = useRef(callback);
  saved.current = callback;

  useEffect(() => {
```

替換為：

```ts
export function usePolling(callback: () => void | Promise<void>, intervalMs: number): void {
  const saved = useRef(callback);
  // ref 的更新要落在 render 之後：render 期間改 ref 會讓 React 讀到不一致的值
  // （並發渲染下 render 可能被丟棄重跑）。無相依陣列＝每次 render 後都更新，
  // 正是此處要的語意——saved.current 永遠是最新的 callback，而下方輪詢的
  // useEffect 相依 [intervalMs]、不因 callback 變動而重啟計時器，這正是本 hook
  // 用 ref 的初衷，修正後仍然成立。
  useEffect(() => {
    saved.current = callback;
  });

  useEffect(() => {
```

- [ ] **Step 3: 確認這條 error 消失（GREEN）**

Run: `cd frontend && npx eslint src/admin/usePolling.ts`
Expected: PASS（無輸出）

- [ ] **Step 4: 確認型別仍正確**

Run: `cd frontend && npm run typecheck`
Expected: PASS（無輸出）

- [ ] **Step 5: Commit**

```bash
cd /home/leo29/kinsun
git add frontend/src/admin/usePolling.ts
git commit -F - <<'EOF'
fix(frontend): usePolling 不再於 render 期間改 ref

saved.current = callback 寫在 render 期間，React 並發渲染下 render 可能被
丟棄重跑，讀到的 ref 值會不一致。改放進無相依陣列的 useEffect——那是這個
hook 的標準寫法（ref 的更新落在 render 之後）。

語意不變：saved.current 仍永遠是最新的 callback，輪詢的 useEffect 仍只相依
[intervalMs]、不因 callback 變動而重啟計時器——那正是本 hook 用 ref 的初衷。

IMPACT：
- 全域訊息流的 5 秒輪詢直接使用此 hook，需人工複驗仍在增量更新（見 plan Task 5）。
- npm run lint 從 8 個 error 減為 7 個。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: 修 7 頁的 effect 內同步 setState

**Files:**
- Modify: `frontend/src/admin/pages/SystemPage.tsx`
- Modify: `frontend/src/admin/pages/ElderTimelinePage.tsx`
- Modify: `frontend/src/admin/pages/TraceDetailPage.tsx`
- Modify: `frontend/src/admin/pages/elder-tabs/AccountTab.tsx`
- Modify: `frontend/src/admin/pages/elder-tabs/MemoryTab.tsx`
- Modify: `frontend/src/admin/pages/elder-tabs/RemindersTab.tsx`
- Modify: `frontend/src/admin/pages/elder-tabs/RiskNotificationsTab.tsx`

**Interfaces:**
- Consumes: Task 1 的 `npm run lint`
- Produces: 無介面變更（皆為元件內部）

七頁形狀相同：`load` 的第一行 `setError(false)` 是同步 setState，而 `useEffect(load, [load])` 會在 effect 中同步呼叫它。修法一律是**把 `setError(false)` 移進成功處理器**，讓兩個 setState 都落在非同步回呼裡。

⚠️ **這是行為變更**：錯誤橫幅原本在重新載入時立刻消失，改後留到成功為止。這是刻意的（不會閃一下「載入中」再跳回錯誤），需人工複驗（Task 5）。

- [ ] **Step 1: 確認 7 條 error 存在（RED）**

Run: `cd frontend && npm run lint`
Expected: FAIL — `✖ 7 problems (7 errors, 0 warnings)`，全為 `react-hooks/set-state-in-effect`

- [ ] **Step 2: 修 `SystemPage.tsx`**

將：

```tsx
  const load = useCallback(() => {
    setError(false);
    listJobs().then(setJobs, () => setError(true));
  }, []);
```

替換為：

```tsx
  const load = useCallback(() => {
    // setError(false) 放進成功處理器而非開頭：開頭是同步 setState，會在
    // useEffect(load, [load]) 中觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    listJobs().then(
      (jobs) => {
        setJobs(jobs);
        setError(false);
      },
      () => setError(true),
    );
  }, []);
```

- [ ] **Step 3: 修 `ElderTimelinePage.tsx`**

將：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    getTimeline(elderId, date).then(setTimeline, () => setError(true));
  }, [elderId, date]);
```

替換為：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    // setError(false) 放進成功處理器：開頭的同步 setState 會在 useEffect 中
    // 觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    getTimeline(elderId, date).then(
      (timeline) => {
        setTimeline(timeline);
        setError(false);
      },
      () => setError(true),
    );
  }, [elderId, date]);
```

- [ ] **Step 4: 修 `TraceDetailPage.tsx`**

⚠️ 此頁的 error state 是 `string | null`（非 boolean），清除值為 `null`。

將：

```tsx
  const load = useCallback(() => {
    if (!traceId) return;
    setError(null);
    getTrace(traceId).then(setTrace, (e) =>
      setError(e?.status === 404 ? strings.trace.notFound : strings.common.loadFailedRefresh),
    );
  }, [traceId]);
```

替換為：

```tsx
  const load = useCallback(() => {
    if (!traceId) return;
    // setError(null) 放進成功處理器：開頭的同步 setState 會在 useEffect 中
    // 觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    getTrace(traceId).then(
      (trace) => {
        setTrace(trace);
        setError(null);
      },
      (e) =>
        setError(e?.status === 404 ? strings.trace.notFound : strings.common.loadFailedRefresh),
    );
  }, [traceId]);
```

- [ ] **Step 5: 修 `AccountTab.tsx`**

將：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    getElderAccount(elderId).then(setData, () => setError(true));
  }, [elderId]);
```

替換為：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    // setError(false) 放進成功處理器：開頭的同步 setState 會在 useEffect 中
    // 觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    getElderAccount(elderId).then(
      (data) => {
        setData(data);
        setError(false);
      },
      () => setError(true),
    );
  }, [elderId]);
```

- [ ] **Step 6: 修 `MemoryTab.tsx`**

將：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    getElderMemory(elderId).then(setData, () => setError(true));
  }, [elderId]);
```

替換為：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    // setError(false) 放進成功處理器：開頭的同步 setState 會在 useEffect 中
    // 觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    getElderMemory(elderId).then(
      (data) => {
        setData(data);
        setError(false);
      },
      () => setError(true),
    );
  }, [elderId]);
```

- [ ] **Step 7: 修 `RemindersTab.tsx`**

將：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    getElderReminders(elderId).then(setData, () => setError(true));
  }, [elderId]);
```

替換為：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    // setError(false) 放進成功處理器：開頭的同步 setState 會在 useEffect 中
    // 觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    getElderReminders(elderId).then(
      (data) => {
        setData(data);
        setError(false);
      },
      () => setError(true),
    );
  }, [elderId]);
```

- [ ] **Step 8: 修 `RiskNotificationsTab.tsx`**

將：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    setError(false);
    listElderRiskNotifications(elderId).then(setItems, () => setError(true));
  }, [elderId]);
```

替換為：

```tsx
  const load = useCallback(() => {
    if (!elderId) return;
    // setError(false) 放進成功處理器：開頭的同步 setState 會在 useEffect 中
    // 觸發連鎖重繪。代價是錯誤橫幅留到成功才消失。
    listElderRiskNotifications(elderId).then(
      (items) => {
        setItems(items);
        setError(false);
      },
      () => setError(true),
    );
  }, [elderId]);
```

- [ ] **Step 9: 確認 frontend lint 全綠（GREEN）**

Run: `cd frontend && npm run lint`
Expected: PASS（無輸出）

- [ ] **Step 10: 確認型別與建置皆過**

Run: `cd frontend && npm run typecheck && npm run build && npm run build:admin`
Expected: 三者皆 PASS

- [ ] **Step 11: Commit**

```bash
cd /home/leo29/kinsun
git add frontend/src/admin/pages/
git commit -F - <<'EOF'
fix(frontend): admin 七頁不再於 effect 中同步 setState

七頁的資料載入是同一個手寫模式：load 的第一行 setError(false) 是同步
setState，而 useEffect(load, [load]) 會在 effect 中同步呼叫它，觸發連鎖重繪。

修法一律是把 setError 移進成功處理器，讓兩個 setState 都落在非同步回呼裡。
刻意不用 if (error) setError(false) 規避——條件式的同步 setState 仍是同步
setState，規則照樣抓，語意還更難懂。

⚠️ 這是行為變更，不只是搬程式碼：錯誤橫幅原本在重新載入時立刻消失，改後
留到成功為止。我們認為改後較好（不會閃一下「載入中」再跳回錯誤），但畫面
確實不同了，且 frontend/ 沒有任何測試守著——只有 tsc 與 build，兩者都證明
不了畫面還能運作。故本 commit 需人工複驗（見 plan Task 5），其中錯誤狀態
那條最重要。

七頁共用同一個手寫模式本身就是重複，值得抽成共用 hook——但那是另一件事，
不該跟「裝 linter」混在同一輪。

IMPACT：
- 觀測後台（/admin）七個畫面的錯誤橫幅時機改變。使用者端零變更。
- npm run lint 從 7 個 error 轉為全綠。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 4: `app/` 的 eslint 設定與 3 處警告

**Files:**
- Create: `app/eslint.config.js`
- Modify: `app/package.json`（devDeps）、`app/package-lock.json`
- Modify: `app/src/app/guardian/elder/[elderId]/index.tsx`、`app/src/app/guardian/home.tsx`、`app/src/app/guardian/notifications.tsx`

**Interfaces:**
- Consumes: 無
- Produces: `cd app && npm run lint` 這個指令（本 Task 結束時全綠）

- [ ] **Step 1: 安裝依賴**

```bash
cd app && npx expo install -- --save-dev eslint eslint-config-expo eslint-plugin-react-hooks
```

若 `expo install` 不接受 `--save-dev` 轉發，改用：

```bash
cd app && npm i -D eslint@9 eslint-config-expo eslint-plugin-react-hooks
```

⚠️ **裝完立刻確認 `app/package.json` 的 `dependencies` 沒有被動到**——只有 `devDependencies` 該多三個。lock file 的差異應該只圍繞這三個套件及其相依。

- [ ] **Step 2: 建立設定檔**

建立 `app/eslint.config.js`：

```js
/**
 * app（長輩／家屬 App，React Native ＋ Expo）的 eslint 設定。
 *
 * 以 eslint-config-expo 為底而非通用的 typescript-eslint：它懂 React Native
 * 慣例——例如 talk.tsx 載入音效的 require("@/assets/sounds/...")，通用設定會
 * 判它 no-require-imports 錯誤，但那是 RN 載入資產的標準寫法。假警報會訓練人
 * 忽略 linter。
 */

const { defineConfig } = require("eslint/config");
const expoConfig = require("eslint-config-expo/flat");
const reactHooks = require("eslint-plugin-react-hooks");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*", ".expo/*"],
  },
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      // react-hooks v7 的 Compiler 層：app.json 已開 experiments.reactCompiler，
      // 編譯器對這些模式的假設就是它能否安全優化的前提，故這層規則對 app/ 不是
      // 學術問題。eslint-config-expo 內建的 react-hooks 較舊、不含這層。
      ...reactHooks.configs.recommended.rules,
    },
  },
]);
```

⚠️ 若 `eslint-config-expo/flat` 的匯入路徑或 `defineConfig` 的用法與實際安裝到的版本不符，**先讀 `app/node_modules/eslint-config-expo/` 的 README 與 package.json 的 exports**，以實際版本為準，不要照抄本計畫。

- [ ] **Step 3: 執行 lint，看實際結果**

Run: `cd app && npm run lint`
Expected: 3 個 `react-hooks/exhaustive-deps` warning（`guardian/elder/[elderId]/index.tsx:76`、`guardian/home.tsx:66`、`guardian/notifications.tsx:53`），皆為 `missing dependency: 'signOutOn401'`。

⚠️ 疊上 Compiler 層後**可能出現 spec 未預期的新 error**（spec 的 app/ 實測是用通用設定跑的，不是 expo 設定 ＋ Compiler 層）。若出現，**停下來回報數量與種類**，不要自行決定關規則。

- [ ] **Step 4: 判斷並修正 3 處警告**

先讀 `app/src/lib/SessionProvider.tsx`，確認 `signOutOn401` 的來源與它是否為穩定參考（是否被 `useCallback` 包過）。

- **若它是穩定參考**（`useCallback` 包裝或定義在元件外）：直接把它補進三處的相依陣列即可。
- **若它每次 render 都是新的函式參考**：補進去會造成無窮迴圈。此時先嘗試在 `SessionProvider` 中以 `useCallback` 把它包成穩定參考（一處修改解三個警告，且對其他使用者也是正確的）。
- **若上述都不可行**：以 `eslint-disable-next-line react-hooks/exhaustive-deps` ＋**一行說明為什麼**放行。⚠️ 不接受無註解的 disable。

- [ ] **Step 5: 確認 app lint 全綠（GREEN）**

Run: `cd app && npm run lint`
Expected: PASS（無警告、無錯誤）

- [ ] **Step 6: 確認型別仍正確**

Run: `cd app && npm run typecheck`
Expected: PASS（無輸出）

- [ ] **Step 7: Commit**

```bash
cd /home/leo29/kinsun
git add app/package.json app/package-lock.json app/eslint.config.js app/src/
git commit -F - <<'EOF'
chore(app): 補上 eslint 設定，讓從未跑過的 lint script 真的能跑

"lint": "expo lint" 這行 script 從 create-expo-app 建專案起就在，但 eslint
從未安裝、也沒有設定檔——它從來沒真正跑過。本 commit 補上缺的那兩塊；script
本身一個字都不用改，它本來就是對的。

以 eslint-config-expo 為底而非通用的 typescript-eslint：它懂 React Native
慣例。實測顯示通用設定會把 talk.tsx 載入音效的 require() 判成錯誤，但那是
RN 載入資產的標準寫法——假警報會訓練人忽略 linter。

疊上 react-hooks v7 的 Compiler 層：app.json 已開 experiments.reactCompiler，
編譯器對這些模式的假設就是它能否安全優化的前提，故這層規則對 app/ 不是學術
問題。expo 設定內建的 react-hooks 較舊、不含這層。

IMPACT：
- 新增三個 devDependency；執行期依賴零變更、App 行為零變更。
- npm run lint 全綠。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 5: CI 加上 lint 步驟，並更正 spec

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `docs/superpowers/specs/2026-07-17-js端引入linting-design.md`

**Interfaces:**
- Consumes: Task 1–4 的兩個 `npm run lint` 指令
- Produces: 無

**這個 Task 是整個計畫唯一的交付價值所在。** 前四個 Task 若沒有它，全都是裝飾品——沒有 CI 擋，沒人會被 linter 擋下來，違規照樣進 main。

- [ ] **Step 1: 加入 frontend 的 lint 步驟**

在 `.github/workflows/ci.yml` 的 frontend job 中，將：

```yaml
      - name: 型別檢查
        run: npm run typecheck
        working-directory: frontend

      - name: 建置
        run: npm run build
        working-directory: frontend
```

替換為：

```yaml
      - name: 型別檢查
        run: npm run typecheck
        working-directory: frontend

      - name: Lint
        run: npm run lint
        working-directory: frontend

      - name: 建置
        run: npm run build
        working-directory: frontend
```

- [ ] **Step 2: 加入 app 的 lint 步驟**

在 `.github/workflows/ci.yml` 的 app job 中，將：

```yaml
      - name: 型別檢查
        run: npm run typecheck
        working-directory: app
```

替換為：

```yaml
      - name: 型別檢查
        run: npm run typecheck
        working-directory: app

      - name: Lint
        run: npm run lint
        working-directory: app
```

兩處皆擺在型別檢查之後：型別錯誤比 lint 違規更根本，先讓更根本的錯誤先報。

- [ ] **Step 3: 驗證 CI 步驟真的會擋**

本機模擬 CI 會跑的指令，確認兩邊皆綠：

Run: `cd frontend && npm run lint && cd ../app && npm run lint && echo "兩邊皆綠"`
Expected: 印出「兩邊皆綠」

接著故意製造一個違規，確認 lint 真的會紅（這是本 Task 的核心斷言——沒有這步，我們不知道 CI 步驟是不是空轉）：

```bash
cd /home/leo29/kinsun/frontend
echo "const 故意沒用到的變數 = 1;" >> src/admin/format.ts
npm run lint    # 應該紅：@typescript-eslint/no-unused-vars
git checkout src/admin/format.ts    # 還原
npm run lint    # 應該綠
```

Expected: 第一次 FAIL（`no-unused-vars`）、還原後 PASS。

⚠️ 務必確認 `git status --short` 在還原後為空。

- [ ] **Step 4: 更正 spec 的論證錯誤**

spec 的「規則嚴格度」節寫道：

> **採 Compiler 層（Leo 核定）**。理由：`app/app.json` 的 `experiments` 已開 `"reactCompiler": true`，這層規則對本專案不是學術問題

這個理由**對 `frontend/` 不成立**——`reactCompiler: true` 只在 `app/app.json`，而 `frontend/` 是 React 18 ＋ Vite ＋ `@vitejs/plugin-react`，沒有跑 React Compiler。諷刺的是那 8 個 error 全都在 frontend/，也就是沒跑編譯器的那一側。

將該段改為：

> **採 Compiler 層（Leo 核定）**。理由分兩邊：`app/` 的 `app.json` 已開 `"reactCompiler": true`，編譯器對這些模式的假設就是它能否安全優化的前提，這層規則對它不是學術問題。`frontend/` 沒跑編譯器（React 18 ＋ Vite），這層規則對它只是效能建議——但連鎖重繪在 React 18 一樣是真的，且兩邊同標準本身有價值（一個專案兩把尺，人會記不住哪邊能寫什麼）。代價是本輪要先修 8 處，而它們全在 frontend/。

- [ ] **Step 5: 全量驗證**

Run: `cd /home/leo29/kinsun && uv run pytest -q 2>&1 | tail -2 && uv run ruff check src/ tests/ && cd frontend && npm run lint && npm run typecheck && npm run build && npm run build:admin && cd ../app && npm run lint && npm run typecheck && echo "全部通過"`
Expected: 後端 1221 passed、ruff All checks passed、印出「全部通過」

- [ ] **Step 6: Commit**

```bash
cd /home/leo29/kinsun
git add .github/workflows/ci.yml docs/superpowers/specs/2026-07-17-js端引入linting-design.md
git commit -F - <<'EOF'
ci: JS 端 lint 納入 CI，讓前四個 commit 不是裝飾品

前四個 commit 把兩邊的 linter 裝好、既有違規修完，但 CI 完全沒跑 JS lint
（frontend job 只有 typecheck／build，app job 只有 typecheck）。沒有這一步，
沒人會被 linter 擋下來，違規照樣進 main——設定檔再漂亮也是裝飾品。

兩處皆擺在型別檢查之後：型別錯誤比 lint 違規更根本，先讓更根本的錯誤先報。

一併更正 spec 的論證錯誤。原文以「app.json 已開 reactCompiler: true」當作
採 Compiler 層的理由，但那只對 app/ 成立——frontend/ 是 React 18 ＋ Vite，
沒跑編譯器。諷刺的是那 8 個 error 全在 frontend/，也就是沒跑編譯器的那一側。
決定不變（連鎖重繪在 React 18 一樣是真的，且兩邊同標準有價值：一個專案兩把
尺，人會記不住哪邊能寫什麼），但理由要誠實。

IMPACT：
- 之後任何 PR 若 JS 端有 lint 違規，CI 會紅。這是本系列的目的。
- ⚠️ 觀測後台七頁的錯誤橫幅時機已於前一 commit 改變，而 frontend/ 無測試；
  人工複驗（見 plan Task 5 Step 7）尚未執行。

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
EOF
```

- [ ] **Step 7: 人工複驗（七條，需 Leo 執行）**

⚠️ `frontend/` 沒有任何測試。Task 3 改了 7 頁 admin，守著它們的只有 `tsc` 與 `npm run build`——**兩者都證明不了畫面還能正常運作**。

起後端與 admin 前端，開 `/admin` 逐條確認：

1. **總覽儀表板**：統計卡與逐時長條圖有資料
2. **全域訊息流**：5 秒輪詢仍在增量更新（Task 2 的 `usePolling` 修改直接影響此處）
3. **系統頁**：排程任務列得出來
4. **長輩時間軸**：對話／推播／風險交錯顯示
5. **單輪鏈路**：各段延遲顯示
6. **長輩各分頁**（帳號／記憶／提醒／風險通知）：資料載得出來
7. ⚠️ **錯誤狀態**：把後端關掉或改錯 API 金鑰，確認錯誤橫幅仍出得來

第 7 條最重要——它正是本系列唯一刻意改變的行為（錯誤橫幅改為留到成功為止）。

---

## Self-Review 紀錄

- **Spec 覆蓋**：元件設計 1→Task 4、2→Task 1、3→Task 3、4→Task 2、5→Task 5；測試策略表→Task 5 Step 3／5；app 的 3 處 exhaustive-deps→Task 4 Step 4；人工複驗七條→Task 5 Step 7。無遺漏。
- **已修正的不一致**：spec 以 `reactCompiler: true` 為兩邊共同理由，但 frontend/ 是 React 18 ＋ Vite、沒跑編譯器 → Task 5 Step 4 一併更正 spec。
- **刻意的中間紅燈**：Task 1 結束時 `npm run lint` 為紅（8 errors），Task 2／3 才轉綠。CI 步驟排在 Task 5，故此中間狀態不擋任何人——若把 CI 步驟提前，Task 1 的 commit 會讓 CI 紅。
- **未寫死的兩處**：Task 4 Step 2 的 `eslint-config-expo/flat` 匯入路徑、Step 4 的 `signOutOn401` 修法——兩者都要求先讀實際安裝的版本／既有程式碼再決定，硬給程式碼會產生與現實不符的指令。
- **範圍外**：`shared/` 不含在本輪（spec 已知限制 1）；抽共用資料載入 hook 不含在本輪（spec 已知限制 2）。
