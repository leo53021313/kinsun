/** 設計 token 的唯一出處是 theme.css；這裡釘住「值沒有被改掉」。
 *
 * ⚠️ 為什麼要測 CSS：這九個色與三級字級是 app/src/lib/theme.ts 的同一組值
 * （docs/dev/12 §3 載明為三端視覺基準）。有人「順手調一下」primary 的話，
 * 網頁與 App 的品牌色就會分岔，而那種偏移沒有人會在 code review 裡看出來。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, expect, it } from "vitest";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const css = readFileSync(path.resolve(__dirname, "theme.css"), "utf-8");

describe("設計 token", () => {
  it.each([
    ["--color-background", "#FFF9F0"],
    ["--color-surface", "#FFFFFF"],
    ["--color-primary", "#C2410C"],
    ["--color-primary-pressed", "#9A3412"],
    ["--color-ink", "#1C1917"],
    ["--color-ink-soft", "#57534E"],
    ["--color-line", "#E7E5E4"],
    ["--color-danger", "#B91C1C"],
    ["--color-success", "#15803D"],
  ])("%s 與 app/src/lib/theme.ts 同值", (token, value) => {
    expect(css).toContain(`${token}: ${value};`);
  });

  it.each([
    ["--text-elder-min", "22px"],
    ["--text-elder-big", "30px"],
    ["--text-elder-huge", "40px"],
  ])("長輩端字級 %s 為 %s", (token, value) => {
    expect(css).toContain(`${token}: ${value};`);
  });

  it("有掛 Tailwind", () => {
    expect(css).toContain('@import "tailwindcss";');
  });
});
