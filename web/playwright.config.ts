import { defineConfig, devices } from "@playwright/test";

/**
 * E2E 打的是**真後端**——這條旅程要驗的就是「前後端合起來會不會動」，
 * 用假資料跑等於什麼都沒驗。跑之前後端必須起來（見 e2e/journey.spec.ts 開頭）。
 *
 * ⚠️ 三家瀏覽器都跑：MediaRecorder 的容器格式與音訊解鎖的行為各家不同，
 * 只測 Chromium 會漏掉正是最容易出事的那兩件。CI 只跑 chromium（見
 * .github/workflows/ci.yml 的 web-e2e job 說明）。
 */
export default defineConfig({
  testDir: "./e2e",
  // 對講機那一段會真的跑 ASR＋LLM＋TTS，慢。
  timeout: 90_000,
  // 共用同一個後端，併行跑會互相污染資料。
  workers: 1,
  use: {
    baseURL: process.env.KINSUN_E2E_BASE_URL ?? "http://localhost:8000",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
