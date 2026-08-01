/**
 * 設計 token 的定義完整性。
 *
 * ⚠️ 刻意**只檢查 token 有沒有被定義，不檢查它的值**：顏色與字級是允許改的
 * （美術本來就會迭代），把色碼釘死只會讓「橘色再暖一點」變成要同時改測試——
 * 而「改測試讓它通過」是個很壞的習慣。
 *
 * 真正值得擋的是另一件事：抄錯 token 名字或刪掉一個，每一處 `bg-primary`
 * 都會默默失效、掉回瀏覽器預設樣式，而那用眼睛看不出來。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, expect, it } from "vitest";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const css = readFileSync(path.resolve(__dirname, "theme.css"), "utf-8");

describe("設計 token", () => {
  it.each([
    "--color-background",
    "--color-surface",
    "--color-primary",
    "--color-primary-pressed",
    "--color-ink",
    "--color-ink-soft",
    "--color-line",
    "--color-danger",
    "--color-success",
  ])("%s 有被定義", (token) => {
    expect(css).toContain(`${token}:`);
  });

  it.each(["--text-elder-min", "--text-elder-big", "--text-elder-huge"])(
    "長輩端字級 %s 有被定義",
    (token) => {
      expect(css).toContain(`${token}:`);
    },
  );

  it("有掛 Tailwind", () => {
    expect(css).toContain('@import "tailwindcss";');
  });
});
