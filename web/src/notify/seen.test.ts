/**
 * 已讀水位（沿用 App 的 ✅ D-12）：以本機時間戳記錄「看到哪裡」。
 *
 * ⚠️ 兩個角色分鍵。共用一支鍵會讓長輩看過提醒之後，家屬的未讀數也跟著被清掉
 * ——而雙欄同時在畫面上，這個 bug 會在展示的第一分鐘就被看到。
 *
 * ⚠️ 角色之外還要分「是誰」（全分支審查發現的 Minor 2，見 `seen.ts` 檔頭）：
 * 同一台瀏覽器換一位長輩上場，水位不可以沿用上一位的。
 */

import { beforeEach, describe, expect, it } from "vitest";

import { saveSession } from "@/session/storage";

import { loadSeenAt, saveSeenAt, unreadCount } from "./seen";

function signIn(role: "elder" | "guardian", displayName: string) {
  saveSession({ role, token: `tok-${displayName}`, display_name: displayName });
}

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
    signIn("guardian", "兒子");
    localStorage.setItem("kinsun_web_seen_at_guardian:兒子", "壞掉");
    expect(loadSeenAt("guardian")).toBe(0);
  });

  it("同一個角色換一位使用者，不會沿用上一位的水位", () => {
    // ⚠️ 彩排一整天的真實情境：上午測阿公（提醒累積）、下午測阿嬤並開過提醒
    // 列表（水位被推到下午）、晚上換回阿公——阿公的舊提醒不可以因此被算成已讀。
    signIn("elder", "阿公");
    saveSeenAt(1754000000, "elder");

    signIn("elder", "阿嬤");
    expect(loadSeenAt("elder")).toBe(0);
    saveSeenAt(1754999999, "elder");

    // 換回阿公：拿回他自己那一支水位，不是阿嬤那支。
    signIn("elder", "阿公");
    expect(loadSeenAt("elder")).toBe(1754000000);
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
