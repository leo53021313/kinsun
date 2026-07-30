/** 家屬通知列表。 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";
import { loadSeenAt } from "@/notify/seen";

import { NotificationsScreen } from "./NotificationsScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function renderScreen(items: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ status: 200, json: async () => envelope(items) }),
  );
  localStorage.setItem(
    "kinsun_web_session_guardian",
    JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
  );
  return render(
    <GuardianSession.Provider>
      <NotificationsScreen />
    </GuardianSession.Provider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("NotificationsScreen", () => {
  it("列出通知，最近的在最上面", async () => {
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
      await screen.findByText("目前沒有通知。金孫有事會第一時間放在這裡。"),
    ).toBeInTheDocument();
  });

  it("開啟就把已讀水位推到最新的那一則", async () => {
    // 家屬不會去按「標示已讀」，看到就算看過。
    renderScreen([{ content: "測試", created_at: 1754000100 }]);
    await screen.findByText("測試");
    await waitFor(() => expect(loadSeenAt("guardian")).toBe(1754000100));
  });

  it("沒有通知時不要把水位歸零", async () => {
    localStorage.setItem("kinsun_web_seen_at_guardian", "1754000000");
    renderScreen([]);
    await screen.findByText("目前沒有通知。金孫有事會第一時間放在這裡。");
    expect(loadSeenAt("guardian")).toBe(1754000000);
  });
});
