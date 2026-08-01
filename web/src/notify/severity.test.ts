/**
 * 後端 `severity` → 橫幅樣式的收斂（2026-08-01）。
 *
 * ⚠️ 這支測的是**執行期**行為，所以刻意用 `as unknown` 餵進型別宣告上「不可能」
 * 的值：`AppNotification` 的型別是編譯期的宣告，執行期真正跑的是 `fetch` 回來
 * 的任意 JSON。只測型別允許的那兩個值，等於只測了不會出事的那一半。
 */

import { describe, expect, it } from "vitest";

import { toBannerSeverity } from "./severity";

describe("toBannerSeverity", () => {
  it('後端送 "alert" 時就是 alert', () => {
    expect(toBannerSeverity("alert")).toBe("alert");
  });

  it('後端送 "notice" 時就是 notice', () => {
    expect(toBannerSeverity("notice")).toBe("notice");
  });

  it("欄位缺席時當成一般通知，不可炸掉", () => {
    // 舊資料，或後端還沒部署到 2026-08-01 之後的版本。
    expect(toBannerSeverity(undefined)).toBe("notice");
    expect(toBannerSeverity(null)).toBe("notice");
  });

  it("認不得的值降級成一般通知（不是升級成警報）", () => {
    // ⚠️ 這個方向是刻意選的，理由與代價寫在 severity.ts 檔頭：未知值最可能來自
    // 「後端新增了較不緊急的種類」，若一律變紅，那種通知一上線畫面會冒出一片
    // 紅色警報，而「警報染多了就沒人看」會反過來弄壞這整個功能。
    expect(toBannerSeverity("emergency")).toBe("notice");
    expect(toBannerSeverity("critical")).toBe("notice");
    expect(toBannerSeverity("")).toBe("notice");
  });

  it("非字串型別（後端回了奇怪的東西）不炸、當成一般通知", () => {
    expect(toBannerSeverity(2)).toBe("notice");
    expect(toBannerSeverity(true)).toBe("notice");
    expect(toBannerSeverity({ severity: "alert" })).toBe("notice");
    expect(toBannerSeverity(["alert"])).toBe("notice");
  });

  it("大小寫必須完全相符——不做寬鬆比對", () => {
    // 寬鬆比對會讓「後端到底送什麼」變成一件說不清楚的事；契約是精確字面值，
    // 對不上就該走保守分支，而不是猜使用者的意思。
    expect(toBannerSeverity("ALERT")).toBe("notice");
    expect(toBannerSeverity("Alert")).toBe("notice");
    expect(toBannerSeverity(" alert")).toBe("notice");
  });
});
