/**
 * 已讀水位（沿用 App 的 ✅ D-12）：以本機時間戳記錄「看到哪裡」。
 *
 * ⚠️ 兩個角色分鍵。共用一支鍵會讓長輩看過提醒之後，家屬的未讀數也跟著被清掉
 * ——而雙欄同時在畫面上，這個 bug 會在展示的第一分鐘就被看到。
 */

import { beforeEach, describe, expect, it } from "vitest";

import { loadSeenAt, saveSeenAt, unreadCount } from "./seen";

beforeEach(() => localStorage.clear());

describe("已讀水位", () => {
  it("沒存過時是 0，代表全部未讀", () => {
    expect(loadSeenAt("guardian")).toBe(0);
  });

  it("存了讀得回來", () => {
    saveSeenAt(1754000000, "guardian");
    expect(loadSeenAt("guardian")).toBe(1754000000);
  });

  it("兩個角色各存各的", () => {
    saveSeenAt(1754000000, "guardian");
    saveSeenAt(1755000000, "elder");
    expect(loadSeenAt("guardian")).toBe(1754000000);
    expect(loadSeenAt("elder")).toBe(1755000000);
  });

  it("存的內容壞掉時當作全部未讀，不要算出 NaN", () => {
    localStorage.setItem("kinsun_web_seen_at_guardian", "壞掉");
    expect(loadSeenAt("guardian")).toBe(0);
  });
});

describe("unreadCount", () => {
  it("比水位新的才算未讀", () => {
    const items = [{ created_at: 300 }, { created_at: 200 }, { created_at: 100 }];
    expect(unreadCount(items, 150)).toBe(2);
  });

  it("水位剛好等於某一則時，那一則算已讀", () => {
    expect(unreadCount([{ created_at: 200 }], 200)).toBe(0);
  });

  it("沒有任何通知時是 0", () => {
    expect(unreadCount([], 0)).toBe(0);
  });
});
