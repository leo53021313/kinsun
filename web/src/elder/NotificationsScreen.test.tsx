/**
 * 長輩看的提醒列表。
 *
 * ⚠️ 與家屬版**刻意不共用元件**：長輩版字級更大、行距更寬、返回鍵是 56px 的
 * 大按鈕。共用會讓兩邊的排版約束互相拉扯——這是 App 版就做過的判斷，沿用。
 */

import { render, screen, waitFor } from "@testing-library/react";
import { formatTime } from "kinsun-shared/format";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { loadSeenAt } from "@/notify/seen";
import { ElderSession } from "@/session/contexts";

import { NotificationsScreen } from "./NotificationsScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function setSession() {
  localStorage.setItem(
    "kinsun_web_session_elder",
    JSON.stringify({ role: "elder", token: "tok", display_name: "王阿嬤" }),
  );
}

/** 401 的處理由呼叫端（`ElderApp`）負責，這裡只要能觀察到它有沒有被通知。 */
const onTokenRevoked = vi.fn();

function renderScreen(items: unknown[]) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, json: async () => envelope(items) }));
  setSession();
  return render(
    <ElderSession.Provider>
      <NotificationsScreen onTokenRevoked={onTokenRevoked} />
    </ElderSession.Provider>,
  );
}

beforeEach(() => {
  localStorage.clear();
  onTokenRevoked.mockClear();
});
afterEach(() => vi.unstubAllGlobals());

describe("NotificationsScreen（長輩版）", () => {
  it("列出提醒", async () => {
    renderScreen([{ content: "該吃降血壓藥囉", created_at: 1754000100 }]);
    expect(await screen.findByText("該吃降血壓藥囉")).toBeInTheDocument();
  });

  it("沒有提醒時說的是長輩聽得懂的話", async () => {
    // 「目前沒有通知」對長輩太生硬，也沒告訴他接下來會怎樣。
    renderScreen([]);
    expect(
      await screen.findByText("現在沒有要提醒您的事。時間到了金孫會跟您說。"),
    ).toBeInTheDocument();
  });

  it("開啟就把已讀水位推到最新，且用長輩自己的那支鍵", async () => {
    renderScreen([{ content: "該吃藥囉", created_at: 1754000100 }]);
    await screen.findByText("該吃藥囉");
    await waitFor(() => expect(loadSeenAt("elder")).toBe(1754000100));
    // ⚠️ 不可以動到家屬的水位——兩欄同時在畫面上，動錯了右邊的未讀數會平白歸零。
    expect(loadSeenAt("guardian")).toBe(0);
  });

  it("已讀水位取清單中最新的一則，不假設 API 回傳順序", async () => {
    // ⚠️ 刻意把「最新」放在中間、不是第一筆：若實作誤用 list[0]，這裡會讀到
    // 100（最舊那一則）而非 300，長輩看過之後未讀數依舊不會歸零。
    renderScreen([
      { content: "a", created_at: 100 },
      { content: "b", created_at: 300 },
      { content: "c", created_at: 200 },
    ]);
    await screen.findByText("a");
    await waitFor(() => expect(loadSeenAt("elder")).toBe(300));
  });

  it("沒有提醒時不要把水位歸零", async () => {
    localStorage.setItem("kinsun_web_seen_at_elder", "1754000000");
    renderScreen([]);
    await screen.findByText("現在沒有要提醒您的事。時間到了金孫會跟您說。");
    expect(loadSeenAt("elder")).toBe(1754000000);
  });

  it("已讀水位寫入失敗不影響已載入的清單", async () => {
    // ⚠️ localStorage.setItem 拋例外（iOS Safari 無痕模式、儲存配額滿）不代表
    // 這輪讀取失敗；若寫入水位的呼叫沒有獨立包 try/catch，例外會被外層的
    // .catch 接住，把剛成功載入的清單整個蓋成「載入失敗」——成功的資料被
    // 錯誤路徑吃掉。
    const original = Storage.prototype.setItem;
    const spy = vi
      .spyOn(Storage.prototype, "setItem")
      .mockImplementation(function (this: Storage, key: string, value: string) {
        if (key.startsWith("kinsun_web_seen_at_")) {
          throw new Error("quota exceeded");
        }
        original.call(this, key, value);
      });
    renderScreen([{ content: "該吃藥囉", created_at: 123 }]);
    expect(await screen.findByText("該吃藥囉")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    spy.mockRestore();
  });

  it("載入中會先顯示載入中，不會先閃過『現在沒有要提醒您的事』", async () => {
    // ⚠️ 用手動控制的 promise，不是 mockResolvedValue：後者在同一個 microtask
    // 就解出結果，測試永遠只看得到「解完之後」那一瞬間，看不出畫面在「還沒解完
    // 之前」顯示的是什麼——這份 plan 已經在這件事上栽過三次。
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    setSession();
    render(
      <ElderSession.Provider>
        <NotificationsScreen onTokenRevoked={onTokenRevoked} />
      </ElderSession.Provider>,
    );
    expect(await screen.findByText("載入中…")).toBeInTheDocument();
    expect(
      screen.queryByText("現在沒有要提醒您的事。時間到了金孫會跟您說。"),
    ).not.toBeInTheDocument();
    resolveFetch({ status: 200, json: async () => envelope([]) });
    expect(
      await screen.findByText("現在沒有要提醒您的事。時間到了金孫會跟您說。"),
    ).toBeInTheDocument();
  });

  it("提醒的時間字級不低於長輩端下限——那一行寫的是「幾點吃藥」", async () => {
    // ⚠️ 全分支審查抓到的 Minor：這一行原本是 `text-base`（16px），低於
    // `--text-elder-min`（22px），是長輩端唯一一處低於下限的已渲染內容。
    // ⚠️ 斷言 class 而非實際尺寸：jsdom 沒有版面計算（同 `TalkScreen.test.tsx`
    // 那條適老化尺寸測試的理由），class 名是這一層唯一測得到的契約。
    renderScreen([{ content: "該吃降血壓藥囉", created_at: 1754000100 }]);
    const time = await screen.findByText(formatTime(1754000100));
    expect(time.className).toContain("text-elder-min");
  });

  it("載入失敗時說的是長輩專用的那句，不是家屬端的「載入失敗，請稍後再試。」", async () => {
    // ⚠️ 全分支審查抓到的 Important：借用 `common.loadFailed` 的話，長輩看完仍然
    // 不知道今天到底有沒有藥要吃——而整條「錯誤取代空狀態」不變量的目的就是不讓
    // 他推論「今天沒事」。這句話要替他排除那個推論，並告訴他還可以問誰。
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
    setSession();
    render(
      <ElderSession.Provider>
        <NotificationsScreen onTokenRevoked={onTokenRevoked} />
      </ElderSession.Provider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "現在讀不到您的提醒，這不代表今天沒有事。請等一下再看一次，或打電話問家人。",
    );
  });

  it("載入失敗時不會同時謊稱『現在沒有要提醒您的事』", async () => {
    // ⚠️ 守住的是「錯誤取代空狀態」而非「錯誤與空狀態並列」：brief 原始版本
    // 把 catch 分支寫成 setItems([]) + setError(...)，畫面會同時顯示這兩句話
    // ——對長輩後果更重，他會以為今天真的沒有任何吃藥提醒。
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
    setSession();
    render(
      <ElderSession.Provider>
        <NotificationsScreen onTokenRevoked={onTokenRevoked} />
      </ElderSession.Provider>,
    );
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(
      screen.queryByText("現在沒有要提醒您的事。時間到了金孫會跟您說。"),
    ).not.toBeInTheDocument();
  });

  it("token 被撤銷（401）時通知呼叫端，而不是叫長輩「稍後再試」", async () => {
    // ⚠️ **全分支審查抓到的 Critical 1** 在提醒列表這一側的樣子：家屬按過「重新
    // 產生長輩綁定碼」之後，這支 token 已經被後端撤銷，「稍後再試」永遠不會成功
    // ——長輩會反覆按鈴鐺，而畫面上沒有任何一條路把他帶回配對畫面。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 401,
        json: async () => ({
          success: false,
          data: null,
          error: { code: "invalid_token", message: "登入已失效" },
          meta: null,
        }),
      }),
    );
    setSession();
    render(
      <ElderSession.Provider>
        <NotificationsScreen onTokenRevoked={onTokenRevoked} />
      </ElderSession.Provider>,
    );
    await waitFor(() => expect(onTokenRevoked).toHaveBeenCalledOnce());
    // 不可以再落到「載入失敗，請稍後再試」那一段：呼叫端這時已經在把他導回配對。
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
