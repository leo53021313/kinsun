/** 家屬通知列表。 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";
import { loadSeenAt } from "@/notify/seen";

import { NotificationsScreen } from "./NotificationsScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function failure(code: string, message: string) {
  return { success: false, data: null, error: { code, message }, meta: null };
}

function setSession() {
  localStorage.setItem(
    "kinsun_web_session_guardian",
    JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
  );
}

function renderScreen(items: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ status: 200, json: async () => envelope(items) }),
  );
  setSession();
  return render(
    <GuardianSession.Provider>
      <NotificationsScreen />
    </GuardianSession.Provider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("NotificationsScreen", () => {
  it("依 API 回傳順序渲染，不會自己重新排序", async () => {
    renderScreen([
      { content: "王阿嬤剛剛說：「我頭有點暈」", created_at: 1754000100 },
      { content: "提醒您：降血壓藥", created_at: 1754000000 },
    ]);
    const items = await screen.findAllByRole("listitem");
    expect(items[0]).toHaveTextContent("我頭有點暈");
  });

  it("沒有通知時顯示引導文字", async () => {
    renderScreen([]);
    expect(
      await screen.findByText("目前沒有通知。阿白有事會第一時間放在這裡。"),
    ).toBeInTheDocument();
  });

  it("開啟就把已讀水位推到最新的那一則", async () => {
    // 家屬不會去按「標示已讀」，看到就算看過。
    renderScreen([{ content: "測試", created_at: 1754000100 }]);
    await screen.findByText("測試");
    await waitFor(() => expect(loadSeenAt("guardian")).toBe(1754000100));
  });

  it("已讀水位取清單中最新的一則，不假設 API 回傳順序", async () => {
    // ⚠️ 刻意把「最新」放在中間、不是第一筆：若實作誤用 list[0]，這裡會讀到
    // 100（最舊那一則）而非 300，家屬看過之後未讀數依舊不會歸零。
    renderScreen([
      { content: "a", created_at: 100 },
      { content: "b", created_at: 300 },
      { content: "c", created_at: 200 },
    ]);
    await screen.findAllByRole("listitem");
    await waitFor(() => expect(loadSeenAt("guardian")).toBe(300));
  });

  it("沒有通知時不要把水位歸零", async () => {
    // ⚠️ 鍵帶著登入者（`notify/seen.ts` 的 Minor 2 修正，2026-08-01）：這裡直接
    // 寫底層鍵是為了「這一輪之前就已經有水位」，故必須與 `setSession()` 的
    // `display_name` 對齊。
    localStorage.setItem("kinsun_web_seen_at_guardian:兒子", "1754000000");
    renderScreen([]);
    await screen.findByText("目前沒有通知。阿白有事會第一時間放在這裡。");
    expect(loadSeenAt("guardian")).toBe(1754000000);
  });

  it("載入中會先顯示載入中，不會先閃過『目前沒有通知』", async () => {
    // ⚠️ 用手動控制的 promise，不是 mockResolvedValue：後者在同一個 microtask
    // 就解出結果，測試永遠只看得到「解完之後」那一瞬間，看不出畫面在「還沒解完
    // 之前」顯示的是什麼——這份 plan 已經在這件事上栽過兩次（P1、Task 6）。
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    setSession();
    render(
      <GuardianSession.Provider>
        <NotificationsScreen />
      </GuardianSession.Provider>,
    );
    expect(await screen.findByText("載入中…")).toBeInTheDocument();
    expect(
      screen.queryByText("目前沒有通知。阿白有事會第一時間放在這裡。"),
    ).not.toBeInTheDocument();
    resolveFetch({ status: 200, json: async () => envelope([]) });
    expect(
      await screen.findByText("目前沒有通知。阿白有事會第一時間放在這裡。"),
    ).toBeInTheDocument();
  });

  it("已讀水位寫入失敗不影響已載入的清單", async () => {
    // ⚠️ localStorage.setItem 拋例外（iOS Safari 無痕模式、儲存配額滿）不代表
    // 這輪讀取失敗；若寫入水位的呼叫沒有獨立包 try/catch，例外會被外層的
    // .catch 接住，把剛成功載入的清單整個蓋成「載入失敗」——成功的資料被
    // 錯誤路徑吃掉。只讓已讀水位那支鍵拋例外，session 鍵維持正常寫入。
    const original = Storage.prototype.setItem;
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(function (this: Storage, key: string, value: string) {
        if (key.startsWith("kinsun_web_seen_at_")) {
          throw new Error("quota exceeded");
        }
        original.call(this, key, value);
      });
    renderScreen([{ content: "測試", created_at: 123 }]);
    expect(await screen.findByText("測試")).toBeInTheDocument();
    expect(screen.queryByText("載入失敗，請稍後再試。")).not.toBeInTheDocument();
    spy.mockRestore();
  });

  it("載入失敗時顯示錯誤，不會同時謊稱『阿白有事會第一時間放在這裡』", async () => {
    // ⚠️ 這一條守住的是「錯誤取代空狀態」而非「錯誤與空狀態並列」：連不上後端
    // 時若同時顯示這句保證，等於對家屬做了一個假承諾——這個產品的價值主張就是
    // 「長輩出事你會第一時間知道」，此刻我們根本沒查到任何東西。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 500,
        json: async () => failure("server_error", "系統忙碌，請稍後再試"),
      }),
    );
    setSession();
    render(
      <GuardianSession.Provider>
        <NotificationsScreen />
      </GuardianSession.Provider>,
    );
    expect(await screen.findByText("載入失敗，請稍後再試。")).toBeInTheDocument();
    expect(
      screen.queryByText("目前沒有通知。阿白有事會第一時間放在這裡。"),
    ).not.toBeInTheDocument();
  });
});

// ── 清單也要分得出危急（裁決 4，2026-08-01）────────────────────
//
// ⚠️ **橫幅紅了但清單看起來一樣的話，家屬捲清單時仍然分不出哪一則是危急**
// ——那是同一個「分不出來」的問題往下一層。橫幅只顯示 3.5 秒就消失，清單才是
// 事後回頭查的地方。
describe("NotificationsScreen 的呈現分級", () => {
  it("危急那則有紅框，一般那則沒有", async () => {
    renderScreen([
      { content: "王阿嬤剛剛說：「我跌倒了」", created_at: 1754000100, severity: "alert" },
      { content: "阿嬤該吃藥了", created_at: 1754000050, severity: "notice" },
    ]);
    const alertItem = await screen.findByText("王阿嬤剛剛說：「我跌倒了」");
    const noticeItem = screen.getByText("阿嬤該吃藥了");

    expect(alertItem.closest("li")!.className).toContain("border-danger");
    expect(noticeItem.closest("li")!.className).not.toContain("border-danger");
  });

  it("危急那則帶「緊急通知」文字標籤——不可只靠顏色（WCAG 1.4.1）", async () => {
    // ⚠️ 讀螢幕的家屬收不到紅框，色覺辨認障礙者也可能收不到；這行字是他們
    // 唯一分得出「這則是危急」的線索。只驗紅框等於只驗了看得見顏色的那群人。
    renderScreen([
      { content: "王阿嬤剛剛說：「我跌倒了」", created_at: 1754000100, severity: "alert" },
    ]);
    expect(await screen.findByText("緊急通知")).toBeInTheDocument();
  });

  it("一般通知不帶「緊急通知」標籤", async () => {
    // 對照組：少了它，「每則都掛標籤」的實作也會讓上一條通過。
    renderScreen([{ content: "阿嬤該吃藥了", created_at: 1754000050, severity: "notice" }]);
    await screen.findByText("阿嬤該吃藥了");
    expect(screen.queryByText("緊急通知")).not.toBeInTheDocument();
  });

  it("後端沒送 severity（舊資料）時當成一般通知，不炸也不變紅", async () => {
    renderScreen([{ content: "舊的通知", created_at: 1754000050 }]);
    const item = await screen.findByText("舊的通知");
    expect(item.closest("li")!.className).not.toContain("border-danger");
    expect(screen.queryByText("緊急通知")).not.toBeInTheDocument();
  });
});
