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
    // ⚠️ 斷言寫死在這裡的完整字面值，**不要**改成 `strings.guardianHome.consent`：
    // 若斷言直接引用同一個常數，往後不管那個常數被改成什麼（包括被截短成只剩最
    // 後一句），畫面渲染的內容永遠跟著改動後的值、測試永遠自己跟自己比對相同、
    // 永遠通過——完全守不住「這段文字不能被縮短」這件事（已用變異驗證證實：見
    // 報告的「變異驗證」一節，把 strings.ts 的 consent 截短後，引用常數版本的斷言
    // 仍然全綠）。這裡刻意複製一份目前的完整內容進測試檔，與 strings.ts 的值分開
    // 比對，才是真的釘住這段法律文字。
    expect(
      await screen.findByText(
        "建立後，金孫會記錄長輩與它的對話內容（文字與語音），用來陪伴關懷、產生每日摘要、" +
          "偵測到危急狀況時通知家人；資料會一直保留，開發團隊為了改善服務可檢視內容。" +
          "按下「建立長輩檔案」即代表您替長輩同意以上事項。",
      ),
    ).toBeInTheDocument();
  });

  it("複製失敗時仍顯示「複製綁定碼」，不謊稱已複製", async () => {
    // 剪貼簿在非安全來源與部分瀏覽器會失敗——這正是這條測試要守的情境。
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
    });
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
    await screen.findByText("AB12CD");
    await userEvent.click(screen.getByRole("button", { name: "複製綁定碼" }));
    // 剪貼簿失敗是非同步的；等它真的跑完，標籤仍應維持原樣，不謊稱已複製。
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "複製綁定碼" })).toBeInTheDocument();
    });
  });

  it("複製成功時標籤變成「已複製」", async () => {
    vi.stubGlobal("navigator", {
      clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
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
    await screen.findByText("AB12CD");
    await userEvent.click(screen.getByRole("button", { name: "複製綁定碼" }));
    expect(await screen.findByRole("button", { name: "已複製" })).toBeInTheDocument();
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
