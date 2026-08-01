/**
 * 後端 `severity` → 橫幅樣式的收斂（2026-08-01）。
 *
 * ⚠️ 這支測的是**執行期**行為，所以刻意用 `as unknown` 餵進型別宣告上「不可能」
 * 的值：`AppNotification` 的型別是編譯期的宣告，執行期真正跑的是 `fetch` 回來
 * 的任意 JSON。只測型別允許的那兩個值，等於只測了不會出事的那一半。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { toBannerSeverity } from "./severity";

let warn: ReturnType<typeof vi.spyOn>;
beforeEach(() => {
  // 靜音並記錄：既有測試會餵一堆認不得的值進來，不攔的話輸出會被 warn 洗版。
  warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
});
afterEach(() => {
  warn.mockRestore();
});

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

  // ── 認不得的值要留痕（T3 審查 Important 2，2026-08-01）─────────
  //
  // ⚠️ 降級本身是對的，**靜默**降級不是：後端新增更嚴重的等級＋後端先部署＋
  // 瀏覽器快取舊 SPA，會讓每一則新等級都被畫成白色禮貌橫幅，而全系統沒有
  // 任何一行留痕，只能靠有人現場肉眼發現。

  it("認不得的值會印出警告，並把原值一起印出來", () => {
    toBannerSeverity("emergency");
    expect(warn).toHaveBeenCalledTimes(1);
    const [message, value] = warn.mock.calls[0];
    expect(String(message)).toContain("[notify]");
    // 原值必須印出來——排查的人第一個要問的就是「那到底是什麼」。
    expect(value).toBe("emergency");
  });

  it("非字串的認不得型別也留痕", () => {
    toBannerSeverity(2);
    toBannerSeverity({ severity: "alert" });
    expect(warn).toHaveBeenCalledTimes(2);
  });

  it("大小寫對不上也算認不得，要留痕", () => {
    // 這是真的契約違反（後端送了我們沒約定的字面值），不是可預期的常態。
    toBannerSeverity("ALERT");
    expect(warn).toHaveBeenCalledTimes(1);
  });

  it("認得的值與「可預期的沒有值」都不留痕——不可製造沒人會讀的雜訊", () => {
    // ⚠️ 這條與上面幾條同等重要：若 `undefined`／`null`／`""` 也 warn，舊資料
    // 會讓 console 每則通知刷一行，真正該看的那一行就被蓋掉了。
    toBannerSeverity("notice");
    toBannerSeverity("alert");
    toBannerSeverity(undefined);
    toBannerSeverity(null);
    toBannerSeverity("");
    expect(warn).not.toHaveBeenCalled();
  });

  it("大小寫必須完全相符——不做寬鬆比對", () => {
    // 寬鬆比對會讓「後端到底送什麼」變成一件說不清楚的事；契約是精確字面值，
    // 對不上就該走保守分支，而不是猜使用者的意思。
    expect(toBannerSeverity("ALERT")).toBe("notice");
    expect(toBannerSeverity("Alert")).toBe("notice");
    expect(toBannerSeverity(" alert")).toBe("notice");
  });
});
