/**
 * 長輩端框內導覽：對講機 ↔ 提醒列表走得到、返回回得來（P3 Task 9）。
 *
 * ⚠️ `NotificationsScreen.test.tsx` 只單獨掛 `<NotificationsScreen />`，驗不到
 * `ElderApp` 的 `switch` 真的把 "notifications" 這個路由接到這支元件、鈴鐺
 * 按下去真的走得到、按返回真的回得去——這道接縫沒有人測過（同
 * `guardian/GuardianApp.test.tsx`「我的長輩 → 通知列表」那條測試補的是同一種
 * 缺口）。`TalkScreen` 依賴 `useTalk`（真實瀏覽器媒體與 WebSocket API），這裡
 * 整支換成假的（同 `TalkScreen.test.tsx` 的做法）——這份測試要驗的是路由接線
 * 本身，不是對講機邏輯。
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElderSession } from "@/session/contexts";

import { ElderApp } from "./ElderApp";

vi.mock("./useTalk", () => ({
  useTalk: () => ({
    avatar: "idle",
    replyText: "按住下面的麥克風說話，或按一下開始、說完再按一下",
    micReady: true,
    pressIn: vi.fn(),
    pressOut: vi.fn(),
  }),
}));

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function renderSignedIn() {
  localStorage.setItem(
    "kinsun_web_session_elder",
    JSON.stringify({ role: "elder", token: "tok", display_name: "王阿嬤" }),
  );
  return render(
    <ElderSession.Provider>
      <ElderApp />
    </ElderSession.Provider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("長輩端框內導覽", () => {
  it("對講機 → 提醒列表走得到，返回回得來", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        json: async () => envelope([{ content: "該吃降血壓藥囉", created_at: 1754000100 }]),
      }),
    );
    renderSignedIn();
    // 一登入就在對講機畫面（見 ElderApp 初始路由）；鈴鐺鍵在 TalkScreen 上。
    await userEvent.click(await screen.findByRole("button", { name: "看金孫的提醒" }));
    expect(await screen.findByRole("heading", { name: "金孫的提醒" })).toBeInTheDocument();
    expect(screen.getByText("該吃降血壓藥囉")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "返回" }));
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
  });
});
