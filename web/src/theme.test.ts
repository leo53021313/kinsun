/**
 * 設計 token 的定義完整性與三端一致性。
 *
 * ⚠️ 原本刻意**只檢查 token 有沒有被定義，不檢查它的值**，理由是顏色允許迭代、
 * 把色碼釘死會讓「橘色再暖一點」變成要同時改測試。那個理由在 2026-08-09 之前
 * 都成立，但它漏掉了另一種失敗：`theme.css` 的檔頭一直宣稱「值與
 * `app/src/lib/theme.ts` 完全相同」，而 app 端在新視覺改版時整組換成靛藍暖黃，
 * web 端沒跟上——**宣稱的不變式默默破了三週，沒有任何測試會紅**。
 *
 * 所以現在分兩層測：
 *
 * 1. **名字存在**（沿用原本的理由）：抄錯 token 名或刪掉一個，每一處
 *    `bg-primary` 都會默默失效、掉回瀏覽器預設樣式，用眼睛看不出來。
 * 2. **值與 app 端一致**：直接讀 `app/src/lib/theme.ts` 比對，而不是把色碼寫死
 *    在測試裡。美術要迭代仍然只改 app 端那一份，這裡會告訴你 web 還沒跟上——
 *    這正是我們要的行為，也正是檔頭那句宣稱的意思。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { describe, expect, it } from "vitest";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const css = readFileSync(path.resolve(__dirname, "theme.css"), "utf-8");
const appTheme = readFileSync(
  path.resolve(__dirname, "../../app/src/lib/theme.ts"),
  "utf-8",
);

/**
 * app 端 `colors` 的 key → web 端 CSS 變數名。
 *
 * ⚠️ 三個名字刻意不同：`text`／`textSoft`／`border` 在 Tailwind 底下會與內建
 * 工具類撞名（`text-*` 是字級、`border-*` 是框線寬度），故 web 端叫
 * `ink`／`ink-soft`／`line`。這是唯一允許的分岔，值仍必須相同。
 */
const COLOR_TOKEN_MAP: Record<string, string> = {
  background: "--color-background",
  backgroundWarmTop: "--color-background-warm-top",
  surface: "--color-surface",
  primary: "--color-primary",
  primaryPressed: "--color-primary-pressed",
  action: "--color-action",
  actionPressed: "--color-action-pressed",
  text: "--color-ink",
  textSoft: "--color-ink-soft",
  border: "--color-line",
  success: "--color-success",
  successText: "--color-success-text",
  warning: "--color-warning",
  warningText: "--color-warning-text",
  danger: "--color-danger",
  dangerText: "--color-danger-text",
  dangerBadge: "--color-danger-badge",
};

/** 從 app 端 `theme.ts` 的 `colors` 區塊取出某個 key 的色碼。 */
function appColor(key: string): string {
  const match = appTheme.match(new RegExp(`\\b${key}:\\s*"(#[0-9A-Fa-f]{3,8})"`));
  if (!match) {
    throw new Error(`app/src/lib/theme.ts 找不到 colors.${key}`);
  }
  return match[1].toUpperCase();
}

/** 從 web 端 `theme.css` 取出某個 CSS 變數的值。 */
function cssVar(name: string): string {
  const match = css.match(new RegExp(`${name}:\\s*([^;]+);`));
  if (!match) {
    throw new Error(`theme.css 找不到 ${name}`);
  }
  return match[1].trim().toUpperCase();
}

describe("設計 token", () => {
  it.each(Object.values(COLOR_TOKEN_MAP))("%s 有被定義", (token) => {
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

describe("與 app 端色票一致（theme.css 檔頭宣稱的不變式）", () => {
  it.each(Object.entries(COLOR_TOKEN_MAP))(
    "colors.%s 與 %s 同值",
    (appKey, cssName) => {
      expect(cssVar(cssName)).toBe(appColor(appKey));
    },
  );
});

describe("對講機狀態態樣 token（新視覺兩層情緒的第一層）", () => {
  /**
   * 五個系統態各有光暈、狀態帶底色與狀態帶文字色。
   *
   * ⚠️ web 端的 `AvatarState` 原本只有四態（`elder/useTalk.ts`），沒有 `error`。
   * token 先備齊五態，畫面層在 W3 補上第五態時才不會又回頭改 token。
   */
  it.each(["idle", "listening", "thinking", "speaking", "error"])(
    "%s 有 glow／pill／ink 三個值",
    (state) => {
      expect(css).toContain(`--talk-${state}-glow:`);
      expect(css).toContain(`--talk-${state}-pill:`);
      expect(css).toContain(`--talk-${state}-ink:`);
    },
  );
});

describe("角色舞台與長輩端尺寸 token", () => {
  it.each([
    ["--avatar-stage-w", "stageW"],
    ["--avatar-stage-h", "stageH"],
    ["--avatar-stage-top", "stageTop"],
  ])("%s 與 app 端 avatar.%s 同值", (cssName, appKey) => {
    const match = appTheme.match(new RegExp(`\\b${appKey}:\\s*(\\d+)`));
    expect(match).not.toBeNull();
    expect(cssVar(cssName)).toBe(`${match![1]}PX`);
  });

  it.each([
    ["--size-elder-talk-button", "talkButton"],
    ["--size-elder-talk-button-small", "talkButtonSmall"],
    ["--size-elder-round-button", "roundButton"],
  ])("%s 與 app 端 elder.%s 同值", (cssName, appKey) => {
    const match = appTheme.match(new RegExp(`\\b${appKey}:\\s*(\\d+)`));
    expect(match).not.toBeNull();
    expect(cssVar(cssName)).toBe(`${match![1]}PX`);
  });
});

describe("圓角與動畫時長 token", () => {
  it.each(["--radius-card", "--radius-control", "--radius-pill"])(
    "%s 有被定義",
    (token) => {
      expect(css).toContain(`${token}:`);
    },
  );

  it.each(["--motion-press", "--motion-state", "--motion-layout"])(
    "%s 有被定義",
    (token) => {
      expect(css).toContain(`${token}:`);
    },
  );
});
