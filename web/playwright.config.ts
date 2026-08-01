import { defineConfig, devices } from "@playwright/test";

/**
 * E2E 打的是**真後端**——這條旅程要驗的就是「前後端合起來會不會動」，
 * 用假資料跑等於什麼都沒驗。跑之前後端必須起來（見 e2e/journey.spec.ts 開頭）。
 *
 * ⚠️ **目前未接進 CI**（`.github/workflows/ci.yml` 沒有、也不存在 `web-e2e` 這個
 * job）——這是刻意的判斷，不是漏做：brief 給的 CI 步驟必要環境變數不全
 * （`GEMINI_API_KEY`／`LINE_CHANNEL_SECRET`／`LINE_CHANNEL_ACCESS_TOKEN` 未設，本地
 * 已實測重現 `ConfigError` 啟動崩潰）且起後端沒有健康檢查等待，貿然掛上去很可能
 * 讓每個人的 PR 一開始就紅。目前只能 `npm run e2e` 在本機／人工執行，見
 * `.superpowers/sdd/2026-07-30-web前端-P4-通知連動與收尾/task-5-report.md`
 * 「CI 的判斷與理由」一節（含之後要接的話可直接沿用的修正清單）。
 *
 * ⚠️ **`baseURL` 預設值有陷阱，見下方 `use.baseURL` 那一行的說明。**
 *
 * ⚠️ 三家瀏覽器都跑：MediaRecorder 的容器格式與音訊解鎖的行為各家不同，
 * 只測 Chromium 會漏掉正是最容易出事的那兩件（本機沙箱環境 webkit 因缺系統
 * 依賴無法啟動，見上述報告；在有完整依賴的機器上三家皆會執行）。
 */
export default defineConfig({
  testDir: "./e2e",
  // ⚠️ 對講機刻意不進 E2E（見 e2e/journey.spec.ts 開頭），兩條情境實測各僅
  // 1.4s／0.25s。90 秒不是為了對講機留的餘裕，是給「後端剛起、demo-status
  // 還在探測中」這種偶發延遲的安全邊界；副作用是**任何真的壞掉的旅程要卡滿
  // 90 秒才報錯**——本機驗證時故意調短過（`--timeout=20000`）以加快疊代，
  // 正式跑（`npm run e2e`）維持這個預設值。
  timeout: 90_000,
  // 共用同一個後端，併行跑會互相污染資料。
  workers: 1,
  use: {
    // ⚠️ **陷阱**：預設值 `http://localhost:8000` 是 `kinsun.sh start` 常駐的那個
    // demo 後端——它的 `DATABASE_URL` 是全庫唯一一份、指向真實 Supabase 雲端專案，
    // **沒有**另外的 demo 專用資料庫。對著它跑「完整旅程」會建立真實的家屬帳號、
    // 長輩檔案與提醒，而後端沒有 `DELETE /elders`（見 `guardian/HomeScreen.tsx`
    // 建立長輩那段註解），寫進去的測試資料**刪不掉**。
    //
    // 跑之前務必先確認自己打的是哪一顆資料庫（見人工驗收清單）；建議在本機或
    // CI 另外起一個指向拋棄式測試庫（`KINSUN_TEST_DATABASE_URL`）的隔離後端，
    // 完整的起法（環境變數清單、mock ASR／bubble TTS）見上方 task-5-report.md。
    //
    // ⚠️ 用 `||` 不用 `??`：本專案的環境變數慣例是 `.env` 整份 export
    // （`scripts/kinsun.sh:195` 的 `set -a; . "$envfile"; set +a`），
    // `KINSUN_E2E_BASE_URL=`（空字串，`.env.example` 出貨值）會被整份 export
    // 成空字串環境變數，而 `??` 只擋 `null`／`undefined`、不擋空字串——
    // 曾實測重現：`baseURL` 變成 `""` 時 Playwright 報 `Cannot navigate to
    // invalid URL`，訊息完全指不出是環境變數的問題。
    baseURL: process.env.KINSUN_E2E_BASE_URL || "http://localhost:8000",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
