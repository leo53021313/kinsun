/** 家屬首頁：長輩列表、新增長輩、綁定碼。 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { HomeScreen } from "./HomeScreen";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function failure(code: string, message: string) {
  return { success: false, data: null, error: { code, message }, meta: null };
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

  // ⚠️ 這一條守的是「錯誤取代空狀態」——本前端最貴的一種失效。後端抖一下（展示
  // 當天最可能的故障）時，若首頁對已經有兩位長輩的家屬說「還沒有長輩檔案，先在
  // 上面建立一位吧」，他會照著做，而後端恢復後那是第三筆**重複且刪不掉**的長輩
  // 檔案（後端沒有 DELETE /elders）。空狀態的文案在連不上的當下是一句假話。
  it("列表載入失敗時只說載入失敗，不可同時說「還沒有長輩檔案」", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 500,
        json: async () => failure("server_error", "系統忙碌，請稍後再試"),
      }),
    );
    renderHome();
    expect(await screen.findByText("載入失敗，請稍後再試。")).toBeInTheDocument();
    expect(screen.queryByText("還沒有長輩檔案，先在上面建立一位吧。")).not.toBeInTheDocument();
  });

  // 「載入失敗」若掛在新增長輩表單底下，讀起來像「建立失敗」，但真正失敗的是列表。
  // 用 DOM 包含關係斷言位置——只比對文字內容守不住這件事。
  it("「載入失敗」不長在新增長輩表單裡面，那會被讀成建立失敗", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 500,
        json: async () => failure("server_error", "系統忙碌，請稍後再試"),
      }),
    );
    renderHome();
    const message = await screen.findByText("載入失敗，請稍後再試。");
    const addSection = screen.getByRole("heading", { name: "新增長輩" }).closest("section");
    expect(addSection).not.toBeNull();
    expect(addSection?.contains(message)).toBe(false);
  });

  it("載入中先顯示載入中，不會先閃過「還沒有長輩檔案」", async () => {
    // ⚠️ 用手動控制的 promise，不是 mockResolvedValue：後者在同一個 microtask 就
    // 解出結果，測試永遠只看得到「解完之後」那一瞬間，看不出載入途中畫面顯示的是
    // 什麼——而「載入途中誤報空狀態」正是上面那條重複建檔的另一半路徑。
    let resolveFetch: (value: unknown) => void = () => {};
    const pending = new Promise((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    renderHome();
    expect(await screen.findByText("載入中…")).toBeInTheDocument();
    expect(screen.queryByText("還沒有長輩檔案，先在上面建立一位吧。")).not.toBeInTheDocument();
    resolveFetch({ status: 200, json: async () => envelope([]) });
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
      })
      // 建立成功後會重打一次列表（見 HomeScreen 的 addElder）。
      .mockResolvedValueOnce({
        status: 200,
        json: async () => envelope([{ elder_id: "e9", name: "阿公", nickname: "阿公" }]),
      });
    vi.stubGlobal("fetch", spy);
    renderHome();
    await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。");
    await userEvent.type(screen.getByLabelText("長輩稱呼"), "阿公");
    await userEvent.click(screen.getByRole("button", { name: "建立長輩檔案" }));
    expect(await screen.findByText("AB12CD")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /阿公/ })).toBeInTheDocument();
  });

  // ⚠️ 這一條守的是「錯誤旗標不可以蓋掉家屬剛建立成功的長輩」。列表載入失敗之後
  // 錯誤訊息佔著清單的位置，樂觀追加的那一筆看不見，而清單其實也還少了他原有的
  // 其他長輩——家屬會以為建立失敗而再按一次，重新走回重複建檔那條路。建立成功
  // 代表後端此刻是通的，重打一次列表同時解決這兩件事。
  it("列表載入失敗後建立成功，會重打列表、錯誤消失且原有的長輩也回來", async () => {
    const spy = vi
      .fn()
      .mockResolvedValueOnce({
        status: 500,
        json: async () => failure("server_error", "系統忙碌，請稍後再試"),
      })
      .mockResolvedValueOnce({
        status: 201,
        json: async () =>
          envelope({ elder_id: "e9", name: "阿公", nickname: "", invite_code: "AB12CD" }),
      })
      .mockResolvedValueOnce({
        status: 200,
        json: async () =>
          envelope([
            { elder_id: "e1", name: "王阿嬤", nickname: "" },
            { elder_id: "e9", name: "阿公", nickname: "" },
          ]),
      });
    vi.stubGlobal("fetch", spy);
    renderHome();
    await screen.findByText("載入失敗，請稍後再試。");
    await userEvent.type(screen.getByLabelText("長輩稱呼"), "阿公");
    await userEvent.click(screen.getByRole("button", { name: "建立長輩檔案" }));

    expect(await screen.findByRole("button", { name: /阿公/ })).toBeInTheDocument();
    // 原有的那位也要回來——只顯示剛建的那一筆會讓家屬以為其他長輩不見了。
    expect(screen.getByRole("button", { name: /王阿嬤/ })).toBeInTheDocument();
    expect(screen.queryByText("載入失敗，請稍後再試。")).not.toBeInTheDocument();
    expect(spy).toHaveBeenCalledTimes(3);
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
      })
      // 建立成功後會重打一次列表（見 HomeScreen 的 addElder）。
      .mockResolvedValueOnce({
        status: 200,
        json: async () => envelope([{ elder_id: "e9", name: "阿公", nickname: "" }]),
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
      })
      // 建立成功後會重打一次列表（見 HomeScreen 的 addElder）。
      .mockResolvedValueOnce({
        status: 200,
        json: async () => envelope([{ elder_id: "e9", name: "阿公", nickname: "" }]),
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

  it("登出鈕按下去就停用，連按兩下不會送出兩次登出", async () => {
    // ⚠️ 用手動控制的 promise：要驗的是「登出請求還在路上的那段時間」按鈕是不是
    // 已經停用了，用 mockResolvedValue 的話那段時間根本不存在。
    // `Button` 早就有 busy 能力（註解還寫明「家屬連按兩下『建立長輩檔案』會建出
    // 兩位長輩」），登出這顆先前沒接上。
    let resolveLogout: (value: unknown) => void = () => {};
    const spy = vi.fn().mockImplementation((_path: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        return new Promise((resolve) => {
          resolveLogout = resolve;
        });
      }
      return Promise.resolve({ status: 200, json: async () => envelope([]) });
    });
    vi.stubGlobal("fetch", spy);
    renderHome();
    await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。");
    const logout = screen.getByRole("button", { name: "登出" });
    const logoutCalls = () =>
      spy.mock.calls.filter(([, init]) => (init as RequestInit | undefined)?.method === "DELETE")
        .length;

    await userEvent.click(logout);
    await waitFor(() => expect(logout).toBeDisabled());
    expect(logout).toHaveAttribute("aria-busy", "true");
    expect(logoutCalls()).toBe(1);
    await userEvent.click(logout);
    expect(logoutCalls()).toBe(1);
    resolveLogout({ status: 204, json: async () => ({}) });
  });

  it("綁定碼旁邊有 QR 圖", async () => {
    const spy = vi
      .fn()
      .mockResolvedValueOnce({ status: 200, json: async () => envelope([]) })
      .mockResolvedValueOnce({
        status: 201,
        json: async () =>
          envelope({ elder_id: "e9", name: "阿公", nickname: "", invite_code: "AB12CD" }),
      })
      // 建立成功後會重打一次列表（見 HomeScreen 的 addElder）。
      .mockResolvedValueOnce({
        status: 200,
        json: async () => envelope([{ elder_id: "e9", name: "阿公", nickname: "" }]),
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
