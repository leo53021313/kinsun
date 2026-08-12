import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/");
});

test("短按兩次可完成一輪對話", async ({ page }) => {
  const microphone = page.getByTestId("mic-button");
  const screen = page.getByTestId("talk-screen");

  await microphone.click();
  await expect(screen).toHaveAttribute("data-state", "listening");
  await expect(screen).toHaveAttribute("data-listening-mode", "tap");
  await expect(page.getByTestId("action-label")).toHaveText("說完再按一下");

  await microphone.click();
  await expect(screen).toHaveAttribute("data-state", "thinking");
  await expect(page.getByTestId("state-label")).toHaveText("想一下喔");
  await expect(screen).toHaveAttribute("data-state", "speaking", { timeout: 2_000 });
  await expect(screen).toHaveAttribute("data-state", "idle", { timeout: 4_000 });
});

test("按住超過 500ms 後，放開可送出", async ({ page }) => {
  const microphone = page.getByTestId("mic-button");
  const screen = page.getByTestId("talk-screen");
  const box = await microphone.boundingBox();
  if (!box) throw new Error("找不到麥克風按鈕位置");

  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect(screen).toHaveAttribute("data-state", "listening");
  await expect(screen).toHaveAttribute("data-listening-mode", "hold", { timeout: 1_000 });
  await expect(page.getByTestId("action-label")).toHaveText("放開送出");

  await page.mouse.up();
  await expect(screen).toHaveAttribute("data-state", "thinking");
});

test("鍵盤可用短按切換方式操作", async ({ page }) => {
  const microphone = page.getByTestId("mic-button");
  const screen = page.getByTestId("talk-screen");

  await microphone.focus();
  await microphone.press("Enter");
  await expect(screen).toHaveAttribute("data-listening-mode", "tap");

  await microphone.press("Enter");
  await expect(screen).toHaveAttribute("data-state", "thinking");
});

test("連線錯誤可重新連線並回到待機", async ({ page }) => {
  const screen = page.getByTestId("talk-screen");

  await page.getByTestId("error-demo").click();
  await expect(screen).toHaveAttribute("data-state", "error");
  await page.getByTestId("retry-button").click();
  await expect(screen).toHaveAttribute("data-state", "thinking");
  await expect(screen).toHaveAttribute("data-state", "idle", { timeout: 2_000 });
});

const researchFixtures = [
  {
    researchState: "idle",
    state: "idle",
    listeningMode: "none",
    label: "準備好了",
  },
  {
    researchState: "listening-tap",
    state: "listening",
    listeningMode: "tap",
    label: "正在聽你說",
  },
  {
    researchState: "listening-hold",
    state: "listening",
    listeningMode: "hold",
    label: "正在聽你說",
  },
  {
    researchState: "thinking",
    state: "thinking",
    listeningMode: "none",
    label: "想一下喔",
  },
  {
    researchState: "speaking",
    state: "speaking",
    listeningMode: "none",
    label: "阿金正在說話",
  },
  {
    researchState: "error",
    state: "error",
    listeningMode: "none",
    label: "連線不太穩",
  },
] as const;

for (const fixture of researchFixtures) {
  test(`研究連結可直接開啟 ${fixture.researchState} 狀態`, async ({ page }) => {
    await page.goto(`/?research_state=${fixture.researchState}`);
    const screen = page.getByTestId("talk-screen");

    await expect(screen).toHaveAttribute("data-research-state", fixture.researchState);
    await expect(screen).toHaveAttribute("data-state", fixture.state);
    await expect(screen).toHaveAttribute("data-listening-mode", fixture.listeningMode);
    await expect(page.getByTestId("state-label")).toHaveText(fixture.label);
  });
}

test("研究用短按 Listening 連結仍可完成送出", async ({ page }) => {
  await page.goto("/?research_state=listening-tap");
  await page.getByTestId("mic-button").click();
  await expect(page.getByTestId("talk-screen")).toHaveAttribute("data-state", "thinking");
});

test("研究用按住 Listening 連結在放開時完成送出", async ({ page }) => {
  await page.goto("/?research_state=listening-hold");
  const microphone = page.getByTestId("mic-button");
  const box = await microphone.boundingBox();
  if (!box) throw new Error("找不到麥克風按鈕位置");

  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect(page.getByTestId("talk-screen")).toHaveAttribute("data-state", "listening");
  await page.mouse.up();
  await expect(page.getByTestId("talk-screen")).toHaveAttribute("data-state", "thinking");
});
