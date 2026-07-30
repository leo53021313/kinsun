/** 家屬首頁：長輩列表、新增長輩、綁定碼。 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { HomeScreen } from "./HomeScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function renderHome(props: Partial<Parameters<typeof HomeScreen>[0]> = {}) {
  localStorage.setItem(
    "kinsun_web_session_guardian",
    JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
  );
  return render(
    <GuardianSession.Provider>
      <HomeScreen onOpenElder={vi.fn()} onOpenNotifications={vi.fn()} {...props} />
    </GuardianSession.Provider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("HomeScreen", () => {
  it("載入後列出長輩", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        json: async () => envelope([{ elder_id: "e1", name: "王阿嬤", nickname: "" }]),
      }),
    );
    renderHome();
    expect(await screen.findByRole("button", { name: /王阿嬤/ })).toBeInTheDocument();
  });

  it("沒有長輩時顯示引導文字", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([]) }));
    renderHome();
    expect(await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。")).toBeInTheDocument();
  });

  it("點長輩會把 id 與稱呼一起交出去", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        json: async () => envelope([{ elder_id: "e1", name: "王阿嬤", nickname: "" }]),
      }),
    );
    const onOpenElder = vi.fn();
    renderHome({ onOpenElder });
    await userEvent.click(await screen.findByRole("button", { name: /王阿嬤/ }));
    expect(onOpenElder).toHaveBeenCalledWith("e1", "王阿嬤");
  });

  it("沒填稱呼就按建立時擋下來，不打後端", async () => {
    const spy = vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([]) });
    vi.stubGlobal("fetch", spy);
    renderHome();
    await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。");
    spy.mockClear();
    await userEvent.click(screen.getByRole("button", { name: "建立長輩檔案" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("請先輸入長輩的稱呼。");
    expect(spy).not.toHaveBeenCalled();
  });

  it("建立成功後把新長輩加進列表，並顯示綁定碼", async () => {
    const spy = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([]) })
      .mockResolvedValueOnce({
        status: 201,
        json: async () =>
          envelope({ elder_id: "e9", name: "阿公", nickname: "阿公", invite_code: "AB12CD" }),
      });
    vi.stubGlobal("fetch", spy);
    renderHome();
    await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。");
    await userEvent.type(screen.getByLabelText("長輩稱呼"), "阿公");
    await userEvent.click(screen.getByRole("button", { name: "建立長輩檔案" }));
    expect(await screen.findByText("AB12CD")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /阿公/ })).toBeInTheDocument();
  });

  it("顯示代辦同意聲明", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([]) }));
    renderHome();
    expect(
      await screen.findByText(/按下「建立長輩檔案」即代表您替長輩同意以上事項/),
    ).toBeInTheDocument();
  });

  it("綁定碼旁邊有 QR 圖", async () => {
    const spy = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([]) })
      .mockResolvedValueOnce({
        status: 201,
        json: async () =>
          envelope({ elder_id: "e9", name: "阿公", nickname: "", invite_code: "AB12CD" }),
      });
    vi.stubGlobal("fetch", spy);
    renderHome();
    await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。");
    await userEvent.type(screen.getByLabelText("長輩稱呼"), "阿公");
    await userEvent.click(screen.getByRole("button", { name: "建立長輩檔案" }));
    await waitFor(() => {
      expect(screen.getByAltText("長輩綁定用的 QR 圖")).toBeInTheDocument();
    });
  });
});
