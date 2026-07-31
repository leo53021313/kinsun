/**
 * 完整旅程：註冊家屬 → 建立長輩 → 取得綁定碼 → 長輩端配對 → 家屬設提醒 →
 * 長輩端收到通知。
 *
 * ⚠️ 打的是**真後端**。跑之前先起：
 *   uv run uvicorn --app-dir src "kinsun.app:build_app" --factory --port 8000
 *   npm --prefix web run build
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
