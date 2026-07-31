/**
 * 完整旅程：註冊家屬 → 建立長輩 → 取得綁定碼 → 長輩端配對 → 家屬設提醒 →
 * 提醒出現在行程清單。
 *
 * ⚠️ **這裡驗的是家屬欄的行程清單，不是長輩欄的通知橫幅**：`app_notifications`
 * 只由排程觸發寫入，建立排程本身不會產生通知，而 `useNotificationFeed` 的
 * `shownUpTo` 一律從 0 起跳（第一輪只重建基準、不補播）——結構上這一步做不到
 * 自動化斷言。「兩欄連動＋通知橫幅」（P4 Task 4 的核心價值）由人工驗收，見
 * `task-5-report.md` 人工驗收清單；`stage/StagePage.tsx`／`notify/` 的單元
 * 測試守著接線本身，但「橫幅真的滑進長輩欄」仍需要人眼確認。
 *
 * ⚠️ 打的是**真後端**，且 `baseURL` 預設 `http://localhost:8000`
 * （`playwright.config.ts` 的既有註解）——**那正是 `kinsun.sh start` 常駐、
 * `DATABASE_URL` 指向真實 Supabase 雲端專案的那個後端，沒有另外的 demo 專用
 * 資料庫**。對著它跑會建立真實的家屬帳號／長輩檔案／提醒，且後端沒有
 * `DELETE /elders`，寫進去的測試資料刪不掉。
 *
 * **建議一律用隔離後端跑**（拋棄式測試庫，不影響任何正式資料）：
 *   DATABASE_URL=postgresql://postgres:kinsun-test@localhost:5433/postgres \
 *   ASR_BACKEND=mock TTS_BACKEND=bubble \
 *   GEMINI_API_KEY=e2e-fake-key-not-a-real-secret \
 *   LINE_CHANNEL_SECRET=e2e-fake-line-secret LINE_CHANNEL_ACCESS_TOKEN=e2e-fake-line-token \
 *   SUPABASE_URL= SUPABASE_SERVICE_KEY= TAVILY_API_KEY= TDX_CLIENT_ID= TDX_CLIENT_SECRET= \
 *   OPIK_ENABLED=false \
 *   uv run uvicorn --app-dir src "kinsun.app:build_app" --factory --host 0.0.0.0 --port 8020
 *
 *   npm --prefix web run build
 *   KINSUN_E2E_BASE_URL=http://localhost:8020 npm --prefix web run e2e
 *
 * 上面三把「必要」環境變數（`GEMINI_API_KEY`／`LINE_CHANNEL_SECRET`／
 * `LINE_CHANNEL_ACCESS_TOKEN`）給的是明顯標記為假的字面值，不是真實憑證——
 * `config.py::_require_present` 這四把鑰匙留空會 fail-fast，而這兩條情境完全
 * 不會呼叫 Gemini 或 LINE。**跑之前先確認自己打的是哪一顆資料庫**，這比
 * 「要不要打 8000」更早一步，且是每次跑都要做的檢查，不是一次性驗收。
 *
 * ⚠️ 每次跑都用不重複的 email。共用同一個後端，固定 email 第二次跑就會撞
 * email_taken，而失敗訊息看起來像功能壞了。
 */

import { expect, test } from "@playwright/test";

function uniqueEmail(): string {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

test("家屬與長輩的完整旅程", async ({ page }) => {
  await page.goto("/demo/");

  // 開場頁：服務可用才進得去。這一步同時驗了 demo-status 端點。
  const start = page.getByRole("button", { name: "開始使用" });
  await expect(start).toBeEnabled({ timeout: 15_000 });
  await start.click();

  // 撕裂展開後兩支手機都在。
  await expect(page.getByRole("region", { name: "家屬的手機" })).toBeVisible();
  await expect(page.getByRole("region", { name: "長輩的手機" })).toBeVisible();

  const guardian = page.getByRole("region", { name: "家屬的手機" });
  const elder = page.getByRole("region", { name: "長輩的手機" });

  // 註冊家屬
  await guardian.getByRole("button", { name: "還沒有帳號？註冊" }).click();
  await guardian.getByLabel("您的稱呼").fill("E2E 兒子");
  await guardian.getByLabel("Email").fill(uniqueEmail());
  await guardian.getByLabel("密碼").fill("correct-horse-8");
  await guardian.getByRole("button", { name: "註冊並登入" }).click();
  await expect(guardian.getByRole("heading", { name: "我的長輩" })).toBeVisible();

  // 建立長輩，拿到綁定碼
  await guardian.getByLabel("長輩稱呼").fill("E2E 阿嬤");
  await guardian.getByRole("button", { name: "建立長輩檔案" }).click();
  await expect(guardian.getByAltText("長輩綁定用的 QR 圖")).toBeVisible();
  const code = await guardian.getByTestId("invite-code").innerText();
  expect(code.trim()).not.toBe("");

  // 長輩端用那組碼配對
  await elder.getByLabel("綁定碼").fill(code.trim());
  await elder.getByRole("button", { name: "開始使用" }).click();
  await expect(elder.getByRole("button", { name: /按住說話/ })).toBeVisible();

  // 家屬替長輩設一個提醒
  await guardian.getByRole("button", { name: /E2E 阿嬤/ }).click();
  await guardian.getByRole("button", { name: "管理行程" }).click();
  await guardian.getByLabel("提醒內容").fill("E2E 降血壓藥");
  await guardian.getByRole("checkbox", { name: "早上" }).click();
  await guardian.getByRole("button", { name: "新增" }).click();
  await expect(guardian.getByText(/E2E 降血壓藥（早上）/)).toBeVisible();
});

test("服務停機時不讓人進去", async ({ page }) => {
  // 攔截狀態端點、假裝資料庫掛了——這比真的去關資料庫安全得多。
  await page.route("**/api/v1/demo-status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        success: true,
        data: { overall: "down", components: { database: "down" } },
        error: null,
        meta: null,
      }),
    }),
  );
  await page.goto("/demo/");
  await expect(page.getByText("服務目前無法使用")).toBeVisible();
  await expect(page.getByRole("button", { name: "開始使用" })).toBeDisabled();
});
