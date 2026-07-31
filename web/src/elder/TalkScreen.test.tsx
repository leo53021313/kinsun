/**
 * 對講機畫面：可及性、停用狀態、以及**按鈕真的把手勢交出去了**。
 * 狀態機本身由 useTalk 的測試涵蓋。
 *
 * ⚠️ 這一份刻意不只驗畫面上有什麼字：這份 spec 連續兩輪（Task 6／7）栽在
 * 「畫面測試沒有斷言按鈕真的送出了什麼」。這裡把 `useTalk` 換成假的之後，
 * 一定要斷言呼叫端到 hook 之間那條線——傳進去的參數、按下去呼叫了哪一支。
 */

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TalkScreen } from "./TalkScreen";
import type { AvatarState } from "./useTalk";

const talkState = vi.hoisted(() => ({
  /** 最後一次傳給 `useTalk` 的參數（驗證呼叫端有把東西交進去）。 */
  options: null as Record<string, unknown> | null,
  avatar: "idle" as AvatarState,
  replyText: "按住下面的麥克風說話，或按一下開始、說完再按一下",
  micReady: true,
  pressIn: vi.fn(),
  pressOut: vi.fn(),
}));

vi.mock("./useTalk", () => ({
  useTalk: (options: Record<string, unknown>) => {
    talkState.options = options;
    return {
      avatar: talkState.avatar,
      replyText: talkState.replyText,
      micReady: talkState.micReady,
      pressIn: talkState.pressIn,
      pressOut: talkState.pressOut,
    };
  },
}));

beforeEach(() => {
  talkState.options = null;
  talkState.avatar = "idle";
  talkState.replyText = "按住下面的麥克風說話，或按一下開始、說完再按一下";
  talkState.micReady = true;
  talkState.pressIn.mockClear();
  talkState.pressOut.mockClear();
});

afterEach(() => vi.unstubAllGlobals());

function renderScreen(
  overrides: Partial<{
    unread: number;
    visible: boolean;
    onOpenNotifications: () => void;
    onLogout: () => void;
    onBindingLost: () => void;
  }> = {},
) {
  const props = {
    unread: 0,
    visible: true,
    onOpenNotifications: vi.fn(),
    onLogout: vi.fn(),
    onBindingLost: vi.fn(),
    ...overrides,
  };
  const view = render(
    <TalkScreen
      token="tok"
      unread={props.unread}
      visible={props.visible}
      onOpenNotifications={props.onOpenNotifications}
      onLogout={props.onLogout}
      onBindingLost={props.onBindingLost}
    />,
  );
  return { ...props, view };
}

function micButton() {
  return screen.getByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
}

describe("TalkScreen", () => {
  it("顯示金孫的回覆", () => {
    renderScreen();
    expect(screen.getByText("按住下面的麥克風說話，或按一下開始、說完再按一下")).toBeInTheDocument();
  });

  it("鈴鐺帶未讀數，讀螢幕的人也聽得到有幾則", () => {
    renderScreen({ unread: 3 });
    expect(screen.getByRole("button", { name: /3 則新的/ })).toBeInTheDocument();
  });

  it("未讀超過 9 時紅點顯示 9+，但可及名稱仍講實際數字", () => {
    // 紅點的位置放不下三位數；聽的人不該因此少掉資訊。
    renderScreen({ unread: 12 });
    expect(screen.getByRole("button", { name: "看金孫的提醒，12 則新的" })).toBeInTheDocument();
    expect(screen.getByText("9+")).toBeInTheDocument();
  });

  it("沒有未讀時鈴鐺只講用途", () => {
    renderScreen({ unread: 0 });
    expect(screen.getByRole("button", { name: "看金孫的提醒" })).toBeInTheDocument();
  });

  it("按鈴鐺會去開提醒畫面", async () => {
    const h = renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "看金孫的提醒" }));
    expect(h.onOpenNotifications).toHaveBeenCalledOnce();
  });

  it.each([
    ["idle", "金孫現在在等您說話"],
    ["listening", "金孫現在在聽"],
    ["thinking", "金孫現在在想"],
    ["speaking", "金孫現在在說話"],
  ])("虛擬形象在 %s 時有可讀的說明，不是只有一個表情符號", (state, label) => {
    talkState.avatar = state as AvatarState;
    renderScreen();
    expect(screen.getByRole("img", { name: label })).toBeInTheDocument();
  });

  it("麥克風鍵有說明手勢的可及名稱", () => {
    renderScreen();
    expect(micButton()).toBeInTheDocument();
  });

  it("適老化尺寸：可點擊目標 ≥56px、字級 ≥22px", () => {
    // ⚠️ 這條約束（`--text-elder-min` 22px 起跳、可點擊目標 ≥56px）是這個專案反覆
    // 修過的東西（Task 7 才剛修過 `ErrorText`／`Field`／`loginLink` 三處），而對講機
    // 是它最要緊的一頁。審查實測：把麥克風鍵改成 40px、回覆字幕改成 `text-sm`，
    // 整份測試仍然全綠——這條約束當時**只靠人工審查守著**。
    //
    // ⚠️ 斷言的是 class 而不是實際尺寸：jsdom 沒有版面計算，`getBoundingClientRect`
    // 一律回 0，`getComputedStyle` 也解不出 Tailwind 的工具類。class 名是這一層
    // 唯一測得到的契約；真正的視覺尺寸由人工驗收把關。
    renderScreen();
    // 104px（與 App 的麥克風鍵同尺寸）
    expect(micButton().className).toContain("size-[104px]");
    // 30px 字幕
    expect(screen.getByRole("status").className).toContain("text-elder-big");
    // 56px 鈴鐺
    expect(screen.getByRole("button", { name: "看金孫的提醒" }).className).toContain("size-14");
    // 56px＋22px 登出
    const logout = screen.getByRole("button", { name: "登出" });
    expect(logout.className).toContain("min-h-14");
    expect(logout.className).toContain("text-elder-min");
  });
});

describe("麥克風鍵真的把手勢交出去", () => {
  it("按下去呼叫 pressIn，放開呼叫 pressOut", () => {
    renderScreen();
    fireEvent.pointerDown(micButton(), { pointerId: 1 });
    expect(talkState.pressIn).toHaveBeenCalledOnce();
    expect(talkState.pressOut).not.toHaveBeenCalled();
    fireEvent.pointerUp(micButton(), { pointerId: 1 });
    expect(talkState.pressOut).toHaveBeenCalledOnce();
  });

  it("按壓被系統中斷（pointercancel）時一樣要結束這一次按壓", () => {
    // ⚠️ 漏接 pointercancel 的後果：狀態機停在「錄音中」、麥克風指示燈一直
    // 亮著，而長輩早就放開了。來電、系統對話框、手指滑掉都會送這個事件。
    renderScreen();
    fireEvent.pointerDown(micButton(), { pointerId: 1 });
    fireEvent.pointerCancel(micButton(), { pointerId: 1 });
    expect(talkState.pressOut).toHaveBeenCalledOnce();
  });

  it("金孫在想的時候麥克風鍵停用", () => {
    // ⚠️ 這裡只斷言 `disabled` 這個屬性，**不**斷言「按下去不會呼叫 pressIn」：
    // 瀏覽器不會把指標事件送給停用的表單控制項，但 `fireEvent` 是直接對節點
    // 派送、繞過那層抑制——那樣的斷言測的是 jsdom 而不是我們的程式碼，而且
    // 永遠不可能通過。真正「還在想的時候不可以再開錄」那條防線在 `useTalk`
    // 自己身上（見 useTalk.test.ts「金孫還在想的時候又按下去」），那一層測得到。
    talkState.avatar = "thinking";
    renderScreen();
    expect(micButton()).toBeDisabled();
  });

  it("拿不到麥克風時麥克風鍵停用", () => {
    talkState.micReady = false;
    renderScreen();
    expect(micButton()).toBeDisabled();
  });
});

describe("交給 useTalk 的東西", () => {
  it("token、visible 與綁定失效回呼都真的傳進去", () => {
    // ⚠️ 沒有這條，`visible` 少傳一個字也沒人會發現——而後果是切到家屬端頁籤
    // 之後麥克風一直開著（同一類坑的第四次）。
    const h = renderScreen({ visible: false });
    expect(talkState.options).toMatchObject({ token: "tok", visible: false });
    expect(talkState.options?.onBindingLost).toBe(h.onBindingLost);
  });
});

describe("登出", () => {
  it("按登出不會直接登出，先問一次並講清楚後果", async () => {
    // ⚠️ 只靠綁定碼配對、家屬還沒替他設過帳密的長輩，一旦登出就自己回不來。
    const h = renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "登出" }));
    expect(h.onLogout).not.toHaveBeenCalled();
    expect(screen.getByRole("alertdialog")).toBeInTheDocument();
  });

  it("確認之後才真的登出", async () => {
    const h = renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "登出" }));
    await userEvent.click(screen.getByRole("button", { name: "確定登出" }));
    expect(h.onLogout).toHaveBeenCalledOnce();
  });

  it("確認列講的是「還沒設過帳密要請家人重新給號碼」，不是叫他去用一組不存在的帳密", async () => {
    // ⚠️ 這顆確認鍵存在的理由，正是「只靠綁定碼配對、家屬還沒替他設過帳密的長輩
    // 一按就自己回不來」——文案若只說「下次要用手機號碼和密碼再登入」，他會安心
    // 地按下確定，然後在登入畫面試一組不存在的密碼。這與本輪修掉的六處文案是同
    // 一種錯誤：叫使用者去找一個不存在的東西。
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "登出" }));
    expect(screen.getByRole("alertdialog")).toHaveTextContent(
      "確定要登出嗎？下次要用手機號碼和密碼登入，還沒設過的話要請家人重新給您一組號碼。",
    );
  });

  it("確認列不宣稱自己是模態的（沒有焦點陷阱就不該這樣宣告）", () => {
    // 宣告 `aria-modal="true"` 會讓螢幕報讀軟體把其餘內容藏起來，但這裡的麥克風鍵
    // 仍然可以按——看得見的人與聽的人會拿到兩種不一樣的畫面。
    renderScreen();
    fireEvent.click(screen.getByRole("button", { name: "登出" }));
    expect(screen.getByRole("alertdialog")).not.toHaveAttribute("aria-modal");
  });

  it("按 Escape 可以關掉確認列", async () => {
    const h = renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "登出" }));
    fireEvent.keyDown(screen.getByRole("alertdialog"), { key: "Escape" });
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(h.onLogout).not.toHaveBeenCalled();
  });

  it("按取消就回到原狀，不登出", async () => {
    const h = renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "登出" }));
    await userEvent.click(screen.getByRole("button", { name: "取消" }));
    expect(h.onLogout).not.toHaveBeenCalled();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
