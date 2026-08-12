/**
 * 「報告」與「我的」兩個分頁的落地頁，以及它們背後那條「目前這位長輩」的規則。
 *
 * ⚠️ 這兩頁刻意很薄，所以測試的重點不是版面，而是**四種狀態各自帶人去哪裡**：
 * 載入中／有長輩／還沒有長輩／載入失敗。薄歸薄，走錯路一樣是死路。
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api";
import { GuardianSession } from "@/session/contexts";

import { GuardianTabsProvider } from "./GuardianTabsProvider";
import { ProfileScreen } from "./ProfileScreen";
import { ReportScreen } from "./ReportScreen";

const listElders = vi.hoisted(() => vi.fn());
vi.mock("./api", () => ({ listElders }));

const SESSION = { role: "guardian" as const, token: "tok", guardian_id: "g1", name: "小明" };

function elder(overrides: Record<string, unknown> = {}) {
  // `Elder` 的真實欄位只有這三個（shared/types.ts）。不照畫面需求推測欄位——
  // App 那批就出過事：摘要畫面推了七個不存在的欄位。
  return { elder_id: "e1", name: "王大明", nickname: "阿公", ...overrides };
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("kinsun_web_session_guardian", JSON.stringify(SESSION));
  listElders.mockReset();
});

afterEach(() => vi.restoreAllMocks());

function renderScreen(which: "report" | "profile" = "report") {
  const onOpenElder = vi.fn();
  const onAddElder = vi.fn();
  const Screen = which === "report" ? ReportScreen : ProfileScreen;
  render(
    <GuardianSession.Provider>
      <GuardianTabsProvider>
        <Screen onOpenElder={onOpenElder} onAddElder={onAddElder} />
      </GuardianTabsProvider>
    </GuardianSession.Provider>,
  );
  return { onOpenElder, onAddElder };
}

describe("報告分頁", () => {
  it("有長輩時顯示稱呼，並把人帶進詳情", async () => {
    listElders.mockResolvedValue([elder()]);
    const h = renderScreen("report");

    expect(await screen.findByText("阿公")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "健康報告（近 30 天）" }));
    expect(h.onOpenElder).toHaveBeenCalledWith(expect.objectContaining({ elder_id: "e1" }));
  });

  it("還沒有長輩時不給死路：帶回首頁去建立", async () => {
    listElders.mockResolvedValue([]);
    const h = renderScreen("report");

    expect(await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "新增長輩" }));
    expect(h.onAddElder).toHaveBeenCalledOnce();
  });

  it("載入失敗時顯示原因並給「再試一次」，按了會重打", async () => {
    listElders.mockRejectedValueOnce(new Error("連線失敗"));
    renderScreen("report");

    expect(await screen.findByRole("alert")).toHaveTextContent("連線失敗");
    listElders.mockResolvedValueOnce([elder()]);
    await userEvent.click(screen.getByRole("button", { name: "再試一次" }));
    expect(await screen.findByText("阿公")).toBeInTheDocument();
  });

  it("401 不顯示錯誤文字——統一處理會把人踢回登入畫面", async () => {
    // ⚠️ 這一條與上一條的差別是刻意的：401 是「token 沒了」，顯示紅字並給「再試
    // 一次」只會讓家屬一直按一個永遠不會成功的鈕。
    listElders.mockRejectedValue(new ApiError(401, "unauthorized", "請重新登入"));
    renderScreen("report");

    await waitFor(() => expect(listElders).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "再試一次" })).not.toBeInTheDocument();
  });
});

describe("「我的」分頁", () => {
  it("標題是這位長輩的稱呼，不是寫死的字", async () => {
    // 設計稿的這一項本來就是長輩的名字。寫死在多位長輩時一定會錯。
    listElders.mockResolvedValue([elder({ nickname: "阿嬤" })]);
    renderScreen("profile");
    expect(await screen.findByRole("heading", { name: "阿嬤" })).toBeInTheDocument();
  });

  it("沒有 nickname 就退回 name", async () => {
    listElders.mockResolvedValue([elder({ nickname: "" })]);
    renderScreen("profile");
    expect(await screen.findByRole("heading", { name: "王大明" })).toBeInTheDocument();
  });

  it("讀不到長輩時才用設計稿的預設字樣", async () => {
    listElders.mockResolvedValue([]);
    renderScreen("profile");
    expect(await screen.findByRole("heading", { name: "阿公" })).toBeInTheDocument();
  });
});
