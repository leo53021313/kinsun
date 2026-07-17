# JS 端引入 linting 設計文件

- 日期：2026-07-17
- 狀態：**已實作**（Task 1–5，PR #56 已併入 main）。⚠️ `/admin` 七條人工複驗尚未執行，其中錯誤狀態那條最重要——那是本設計唯一刻意改變的行為。本文已依實作結果更正三處：採 Compiler 層的理由（原文對 frontend/ 不成立）、app/ 的違規數（原文漏記 2 個 error）、frontend/ 設定漏寫 `js.configs.recommended` 及其假警報處置。
- 相關決策：app/ 與 frontend/ 都做並加進 CI（Leo 核定）、採 React Compiler 層規則並於本輪修完既有違規（Leo 核定）、兩邊不共用設定

## 背景與動機

`app/package.json` 有一行 `"lint": "expo lint"`。它從來沒有真正跑過——eslint 未安裝、無設定檔。那是 `create-expo-app` 建專案時留下的樣板 script，沒人設定過它。`frontend/` 更徹底：連那行 script 都沒有。

**這個專案的 JS 端從來沒有 linter。**

對照後端：`pyproject.toml` 有完整的 ruff 設定（`select = ["E", "W", "F", "I", "B", "UP"]`、line-length 100），CI 有 `Ruff lint` 步驟擋門。兩邊的標準落差是本設計要補的缺口。

### 核心洞察：沒有 CI 就是裝飾品

`.github/workflows/ci.yml` 的 frontend job 只跑 `typecheck`／`build`／`build:admin`，app job 只跑 `typecheck`。**CI 完全沒跑任何 JS lint。**

所以「把設定檔補好」本身沒有價值——沒有 CI 擋，沒人會被它擋下來，違規照樣進 main。CI 步驟不是本設計的附加項，而是它唯一的交付價值所在。

## 方案選擇

### 設定：兩套，不共用

| 方案 | 說明 | 結論 |
| :--- | :--- | :--- |
| A：app/ 與 frontend/ 各一套 | app 用 `eslint-config-expo`，frontend 用 `typescript-eslint` | ✅ 採用 |
| B：共用一套 base config | 兩邊繼承同一份，減少重複 | ❌ 見下方實測 |

**實測否決 B**：用通用的 `typescript-eslint` 量 `app/`，`app/src/app/elder/talk.tsx` 的兩行 `require("@/assets/sounds/record-start.wav")` 被判 `@typescript-eslint/no-require-imports` 錯誤——但那是 **React Native 載入資產的標準寫法**，不是錯。`eslint-config-expo` 懂這個慣例，通用設定不懂。

app/ 是 React Native、frontend/ 是瀏覽器 Vite app，執行環境與慣例本就不同。共用一套只會製造假警報，而假警報會訓練人忽略 linter。

### 規則嚴格度：採 React Compiler 層

`eslint-plugin-react-hooks` 有兩層規則：

- **經典層**：rules-of-hooks、exhaustive-deps
- **Compiler 層**（v7）：額外抓 `set-state-in-effect`（effect 裡同步 setState 會觸發連鎖重繪）、`refs`（render 期間改 ref）等

實測結果：

| 目標 | 經典層 | Compiler 層 |
| :--- | :--- | :--- |
| `app/` | 1 warning | 2 errors ＋ 3 warnings（另 2 個 `require()` error 為通用設定的假警報，見上，不計入） |
| `frontend/` | 幾乎全綠 | 8 errors |

實作時發現 `app/` 那 2 個 `set-state-in-effect` error（`medications.tsx`、`appointments.tsx`）**也是假警報**，與 `frontend/` 那 7 個性質不同：這兩處的 `reload` 是 async，每一個 setState 都在 `await` 之後，effect 的同步執行期間一個都不會跑；規則只是無法跨函式邊界分析（已驗證 `void reload()` 也壓不掉，非寫法問題）。故以 `eslint-disable` ＋ 理由放行。`frontend/` 那 7 個則是 `setError(false)` 寫在函式開頭、確實同步，是真的。

**採 Compiler 層（Leo 核定）**。理由分兩邊：`app/` 的 `app.json` 已開 `"reactCompiler": true`，編譯器對這些模式的假設就是它能否安全優化的前提，這層規則對它不是學術問題。`frontend/` 沒跑編譯器（React 18 ＋ Vite），這層規則對它只是效能建議——但連鎖重繪在 React 18 一樣是真的，且兩邊同標準本身有價值（一個專案兩把尺，人會記不住哪邊能寫什麼）。代價是本輪要先修 8 處，而它們全在 frontend/。

## 元件設計

### 1. `app/` 的設定：`app/eslint.config.js`

`eslint-config-expo` 為底（懂 RN 慣例），疊上 `eslint-plugin-react-hooks` 的 Compiler 層。

新增 devDependencies：`eslint`、`eslint-config-expo`、`eslint-plugin-react-hooks`。

`"lint": "expo lint"` 這行 script **維持不動**——它本來就是對的，只是從來沒有設定檔可讀。

### 2. `frontend/` 的設定：`frontend/eslint.config.js`

`js.configs.recommended` ＋ `typescript-eslint` recommended ＋ react-hooks Compiler 層 ＋ `eslint-plugin-react-refresh`（Vite HMR 專用規則，確保元件檔只匯出元件）。

⚠️ `js.configs.recommended` 的 `no-irregular-whitespace` 必須設 `skipTemplates: true, skipJSXText: true`：全形空白（U+3000）在中文文案裡是正當排版（`` `　token 入 ${input}／出 ${output}` ``），AGENTS.md 也明訂用全形標點，預設卻把它判成 error——實測 20 處全是假警報。只在**文案**放行，**程式碼**裡仍然抓：識別字或運算子之間冒出全形空白從來不是刻意的，那種才是這條規則要防的 bug。這與否決「共用設定」是同一個原則：假警報會訓練人忽略 linter。

新增 devDependencies：`eslint`、`typescript-eslint`、`eslint-plugin-react-hooks`、`eslint-plugin-react-refresh`。
新增 script：`"lint": "eslint src"`。

### 3. 修 `frontend/` 的 7 處 `set-state-in-effect`

七頁形狀完全相同（`SystemPage`、`ElderTimelinePage`、`TraceDetailPage`、`AccountTab`、`MemoryTab`、`RemindersTab`、`RiskNotificationsTab`）：

```tsx
const load = useCallback(() => {
  setError(false);                                    // ← effect 裡的同步 setState
  fetchThing().then(setData, () => setError(true));
}, [deps]);

useEffect(load, [load]);
```

改為把 `setError(false)` 移進成功處理器，兩個 setState 就都落在非同步回呼裡：

```tsx
const load = useCallback(() => {
  fetchThing().then(
    (d) => {
      setData(d);
      setError(false);
    },
    () => setError(true),
  );
}, [deps]);

useEffect(load, [load]);
```

⚠️ **這是行為變更，不只是搬程式碼**：錯誤橫幅原本在重新載入時**立刻**消失，改後會**留到成功為止**。我們認為改後較好（不會閃一下「載入中」再跳回錯誤），但它確實改變了畫面。

⚠️ **不可用 `if (error) setError(false)` 規避**：條件式的同步 setState 仍是同步 setState，規則照樣會抓，而且語意更難懂。

### 4. 修 `usePolling.ts` 的 `refs`

```tsx
const saved = useRef(callback);
saved.current = callback;   // ← render 期間改 ref
```

改為標準寫法（ref 的更新落在 render 之後）：

```tsx
const saved = useRef(callback);
useEffect(() => {
  saved.current = callback;
});
```

無相依陣列即「每次 render 後都更新」，正是此處要的語意：`saved.current` 永遠是最新的 callback，而輪詢的 `useEffect`（相依 `[intervalMs]`）不會因 callback 變動而重啟計時器——這正是本 hook 用 ref 的初衷，修正後仍然成立。

### 5. CI 兩個 lint 步驟

`.github/workflows/ci.yml`：

- frontend job：於「型別檢查」之後、「建置」之前插入 `npm run lint`（working-directory: frontend）
- app job：於「型別檢查」之後插入 `npm run lint`（working-directory: app）

擺在 typecheck 之後：型別錯誤比 lint 違規更根本，先讓更根本的錯誤先報。

## 錯誤處理

不適用——本設計無執行期程式碼。lint 違規即 CI 紅燈，這是預期行為。

## 設定（環境變數）

無。

## 資料庫遷移

無。

## 測試策略

**本設計沒有、也不該有新的自動化測試**：它交付的是設定檔與 CI 步驟，而「設定有沒有生效」的驗證就是 CI 本身會不會紅。為 lint 設定寫測試是套套邏輯。

驗證方式：

| 項目 | 方法 |
| :--- | :--- |
| 兩邊 lint 設定可跑且全綠 | `cd app && npm run lint`、`cd frontend && npm run lint` |
| lint 真的會擋 | 故意寫一個違規（如未使用變數），確認 `npm run lint` 紅；還原 |
| 修改未破壞型別 | `npm run typecheck`（兩邊） |
| 修改未破壞建置 | `cd frontend && npm run build && npm run build:admin` |
| 後端不受影響 | `uv run pytest`（應與現在同為 1221 passed） |

### ⚠️ frontend/ 沒有任何測試，這是本設計最大的風險

要改 7 頁 admin，而守著它們的只有 `tsc` 與 `npm run build`——**兩者都證明不了畫面還能正常運作**。型別對、建置過，不代表資料載得出來。

故本設計**必須**以人工複驗收尾（開 `/admin`，逐頁確認）：

1. 總覽儀表板：統計卡與逐時長條圖有資料
2. 全域訊息流：5 秒輪詢仍在增量更新（`usePolling` 的修改直接影響此處）
3. 系統頁：排程任務列得出來
4. 長輩時間軸：對話／推播／風險交錯顯示
5. 單輪鏈路：各段延遲顯示
6. 長輩各分頁（帳號／記憶／提醒／風險通知）：資料載得出來
7. **錯誤狀態**：把後端關掉或改錯 API 金鑰，確認錯誤橫幅仍出得來（第 3 節的行為變更直接影響此處）

第 7 條最重要——它正是本設計唯一刻意改變的行為。

## 影響範圍

- **新增**：`app/eslint.config.js`、`frontend/eslint.config.js`
- **修改**：`app/package.json`＋`app/package-lock.json`（devDeps）、`frontend/package.json`＋`frontend/package-lock.json`（devDeps ＋ lint script）、`.github/workflows/ci.yml`（兩個步驟）、`frontend/src/admin/usePolling.ts`、`frontend/src/admin/pages/` 下 7 個元件、`app/src/lib/SessionProvider.tsx` 一帶的 `exhaustive-deps` 警告（3 處，見下）
- **對外行為變更**：admin 後台的錯誤橫幅在重新載入時留到成功為止（第 3 節）。**使用者端（長輩 App、家屬 App）零變更。**
- **無破壞性變更**：後端完全不受影響。

### app/ 的 3 處 exhaustive-deps 警告

實測顯示 `app/` 有 3 處 `React Hook useCallback has a missing dependency: 'signOutOn401'`。這些是 **warning 而非 error**，但既然本輪要讓 lint 有意義，warning 也應清掉——否則第一天就留下「反正只是 warning」的先例，linter 的權威從此打折。

實作時逐處判斷：能安全補進相依陣列就補；若補了會造成無窮迴圈（`signOutOn401` 若非 `useCallback` 包裝，每次 render 都是新的函式參考），則要嘛把它包成穩定參考，要嘛以 `eslint-disable-next-line` ＋**一行說明為什麼**放行。不接受無註解的 disable。

## 已知限制

### 1. `shared/` 不在本輪範圍

`shared/`（`client.ts`、`envelope.ts`、`format.ts`、`terms.ts`、`types.ts`）是 app 與 frontend 共用的 TS 套件，同樣沒有 linter。本輪刻意不含它：Leo 核定的範圍是 app/ 與 frontend/，而 `shared/` 是純資料與 HTTP 邏輯、無 React hooks，本設計採用的 Compiler 層規則對它幾乎沒有作用。日後若要補，它需要第三套設定（無 React、無 RN）。

### 2. Compiler 層規則只擋得住新寫的 hooks 問題

修完這 8 處不代表 admin 的資料載入模式從此正確——lint 抓的是「effect 裡同步 setState」這個特定形狀，不是「這個元件的狀態管理設計得好不好」。七頁共用同一個手寫模式（`useCallback` ＋ `useEffect(load, [load])` ＋ 手動 error state）本身就是重複，值得抽成共用 hook，但那是另一件事，不在本輪。

### 3. `expo lint` 的行為由 Expo CLI 決定

`app/` 走 `expo lint` 而非直接 `eslint`，好處是與 Expo 工具鏈一致、日後 SDK 升級時 Expo 會處理設定遷移；代價是我們少一層控制（它決定要 lint 哪些檔案）。若日後需要精確控制範圍，改為直接呼叫 `eslint` 即可，設定檔不必動。
