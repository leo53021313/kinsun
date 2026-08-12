/** 當天對話紀錄：跨日界線、上限、以及壞資料不可拖垮對講機。 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { appendTurn, clearToday, loadToday } from "./todayLog";

const KEY = "kinsun.todayLog.v1";

function turn(reply: string) {
  return { at: 1_754_000_000_000, said: "今天天氣真好", reply };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

describe("todayLog", () => {
  it("寫進去讀得回來，順序照寫入順序", async () => {
    await appendTurn(turn("是啊"));
    await appendTurn(turn("要不要出去走走"));
    expect((await loadToday()).map((t) => t.reply)).toEqual(["是啊", "要不要出去走走"]);
  });

  it("跨日自動視為空——不必等清除排程", async () => {
    // 設計上「只留當天」：直接偽造一筆昨天的紀錄，讀出來要是空的。
    localStorage.setItem(
      KEY,
      JSON.stringify({ day: "2020-01-01", turns: [turn("昨天的話")] }),
    );
    expect(await loadToday()).toEqual([]);
  });

  it("跨日之後再寫入，舊的那天不會被接在後面", async () => {
    localStorage.setItem(
      KEY,
      JSON.stringify({ day: "2020-01-01", turns: [turn("昨天的話")] }),
    );
    await appendTurn(turn("今天的話"));
    expect((await loadToday()).map((t) => t.reply)).toEqual(["今天的話"]);
  });

  it("超過 200 筆時丟掉最舊的，留最新的", async () => {
    // 長輩找的通常是剛才那句，不是今天第一句。
    for (let i = 0; i < 205; i += 1) {
      await appendTurn(turn(`第 ${i} 句`));
    }
    const turns = await loadToday();
    expect(turns).toHaveLength(200);
    expect(turns[0].reply).toBe("第 5 句");
    expect(turns.at(-1)?.reply).toBe("第 204 句");
  });

  it("清除之後是空的", async () => {
    await appendTurn(turn("是啊"));
    await clearToday();
    expect(await loadToday()).toEqual([]);
  });

  it("儲存區壞掉時當作沒有，不可把例外丟給對講機", async () => {
    // 無痕模式與配額用盡時 `localStorage` 會直接丟例外。這是加分功能，
    // 不可以讓它擋住長輩講話——三支 API 都必須吞掉。
    localStorage.setItem(KEY, "{ 這不是 JSON");
    expect(await loadToday()).toEqual([]);

    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("QuotaExceededError");
    });
    await expect(appendTurn(turn("是啊"))).resolves.toBeUndefined();

    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new Error("SecurityError");
    });
    await expect(clearToday()).resolves.toBeUndefined();
  });
});
