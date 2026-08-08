/**
 * 對講機畫面：可及性、停用狀態、以及**按鈕真的把手勢交出去了**。
 * 狀態機本身由 useTalk 的測試涵蓋。
 *
 * ⚠️ 這一份刻意不只驗畫面上有什麼字：這份 spec 連續兩輪（Task 6／7）栽在
 * 「畫面測試沒有斷言按鈕真的送出了什麼」。這裡把 `useTalk` 換成假的之後，
 * 一定要斷言呼叫端到 hook 之間那條線——傳進去的參數、按下去呼叫了哪一支。
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TalkScreen } from "./TalkScreen";
import { loadToday } from "./todayLog";
import type { AvatarState } from "./useTalk";

const talkState = vi.hoisted(() => ({
  /** 最後一次傳給 `useTalk` 的參數（驗證呼叫端有把東西交進去）。 */
  options: null as Record<string, unknown> | null,
  avatar: "idle" as AvatarState,
  replyText: "按住下面的麥克風說話，或按一下開始、說完再按一下",
  transcript: "",
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
      transcript: talkState.transcript,
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
  talkState.transcript = "";
  talkState.micReady = true;
  localStorage.clear();
  talkState.pressIn.mockClear();
  talkState.pressOut.mockClear();
});

afterEach(() => vi.unstubAllGlobals());

function renderScreen(
  overrides: Partial<{
    unread: number;
    visible: boolean;
    onOpenNotifications: () => void;
    onOpenHistory: () => void;
    onLogout: () => void;
    onBindingLost: () => void;
    onTokenRevoked: () => void;
  }> = {},
) {
  const props = {
    unread: 0,
    visible: true,
    onOpenNotifications: vi.fn(),
    onOpenHistory: vi.fn(),
    onLogout: vi.fn(),
    onBindingLost: vi.fn(),
    onTokenRevoked: vi.fn(),
    ...overrides,
  };
  /**
   * ⚠️ 每次都建**新的** element，不可重用同一個參考：React 對referentially 相同、
   * props 也相同的 element 會直接跳過重繪，`talkState` 改了也不會被讀到——症狀是
   * 「改了狀態卻什麼都沒變」，很容易被誤判成元件壞掉。
   */
  const build = () => (
    <TalkScreen
      token="tok"
      unread={props.unread}
      visible={props.visible}
      onOpenNotifications={props.onOpenNotifications}
      onOpenHistory={props.onOpenHistory}
      onLogout={props.onLogout}
      onBindingLost={props.onBindingLost}
      onTokenRevoked={props.onTokenRevoked}
    />
  );
  const view = render(build());
  /**
   * 用同一組 props 重繪。
   *
   * `useTalk` 的假替身在每次 render 時才讀 `talkState`，所以「改 talkState 再重繪」
   * 就等於模擬狀態轉場——這是驗收合／展開這種**跨狀態**行為唯一的辦法，光看單一
   * 狀態的快照看不出「說完之後才收合」。
   */
  return { ...props, view, container: view.container, rerender: () => view.rerender(build()) };
}

function micButton() {
  return screen.getByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
}

describe("TalkScreen", () => {
  it("顯示阿白的回覆", () => {
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
    expect(screen.getByRole("button", { name: "看阿白的提醒，12 則新的" })).toBeInTheDocument();
    expect(screen.getByText("9+")).toBeInTheDocument();
  });

  it("沒有未讀時鈴鐺只講用途", () => {
    renderScreen({ unread: 0 });
    expect(screen.getByRole("button", { name: "看阿白的提醒" })).toBeInTheDocument();
  });

  it("按鈴鐺會去開提醒畫面", async () => {
    const h = renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "看阿白的提醒" }));
    expect(h.onOpenNotifications).toHaveBeenCalledOnce();
  });

  it.each([
    ["idle", "準備好了", "我在這裡等您"],
    ["listening", "正在聽你說", "說完放開就好"],
    ["thinking", "想一下喔", "馬上就好"],
    ["speaking", "阿白正在說話", "聽完再按一下就好"],
    ["error", "連線不太穩", "我暫時聽不到您說話"],
  ])("狀態帶在 %s 時用可見文字說出狀態（W3b 起不再靠 aria-label）", (state, label, sub) => {
    // W3a 之前狀態掛在舞台的 aria-label 上。狀態帶到位後改用可見文字——看得見的
    // 人與聽的人拿到同一份資訊，也不會有「同一個狀態兩套說法」的漂移。
    talkState.avatar = state as AvatarState;
    renderScreen();
    const band = screen.getByTestId("talk-status-band");
    expect(band).toHaveTextContent(label);
    expect(band).toHaveTextContent(sub);
    // 三重編碼（規則 6）：文字之外還要有圖示與底色，拿掉顏色仍讀得懂。
    expect(band.querySelector("svg")).toBeTruthy();
    expect(band.style.backgroundColor).toContain(`--talk-${state}-pill`);
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
    // 132px 主鍵（新視覺的長輩端主要態，`theme.ts` 的 elder.talkButton）
    expect(micButton().style.width).toBe("132px");
    expect(micButton().style.height).toBe("132px");
    // 24px 回話內文（與 App 的 replyText 同值；仍高於 22px 下限）
    expect(screen.getByRole("status").className).toContain("text-[24px]");
    // 60px 頁首圓鈕（elder.roundButton）
    expect(screen.getByRole("button", { name: "看阿白的提醒" }).className).toContain(
      "size-[var(--size-elder-round-button)]",
    );
    // 56px＋22px 登出
    const logout = screen.getByRole("button", { name: "登出" });
    expect(logout.className).toContain("min-h-14");
    expect(logout.className).toContain("text-elder-min");
  });

  it("未讀紅點的數字同樣不小於 22px——那顆紅點是給看得見的長輩的捷徑", () => {
    // ⚠️ 全分支審查抓到的 Minor：紅點原本是 `text-sm`（14px）。它是 `aria-hidden`
    // 的捷徑、真正的數字在 aria-label 裡，但那條捷徑正是給**看得見的長輩**用的，
    // 14px 的數字他看不清，捷徑就不存在。
    // ⚠️ 目前 `ElderApp` 寫死 `unread={0}`，這一段在正式畫面上還不會渲染，P4 接上
    // 輪詢時才會現形——沒有這條測試，那時不會有人記得回來看它的字級。
    renderScreen({ unread: 3 });
    expect(screen.getByText("3").className).toContain("text-elder-min");
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

  it("阿白在想的時候麥克風鍵停用", () => {
    // ⚠️ 這裡只斷言 `disabled` 這個屬性，**不**斷言「按下去不會呼叫 pressIn」：
    // 瀏覽器不會把指標事件送給停用的表單控制項，但 `fireEvent` 是直接對節點
    // 派送、繞過那層抑制——那樣的斷言測的是 jsdom 而不是我們的程式碼，而且
    // 永遠不可能通過。真正「還在想的時候不可以再開錄」那條防線在 `useTalk`
    // 自己身上（見 useTalk.test.ts「阿白還在想的時候又按下去」），那一層測得到。
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
  it("token、visible 與兩支登入失效回呼都真的傳進去", () => {
    // ⚠️ 沒有這條，`visible` 少傳一個字也沒人會發現——而後果是切到家屬端頁籤
    // 之後麥克風一直開著（同一類坑的第四次）。
    // ⚠️ `onTokenRevoked` 少傳的後果同樣看不出來：畫面完全正常，但長輩在家屬按過
    // 「重新產生綁定碼」之後永遠回不到配對畫面（全分支審查的 Critical 1）。
    const h = renderScreen({ visible: false });
    expect(talkState.options).toMatchObject({ token: "tok", visible: false });
    expect(talkState.options?.onBindingLost).toBe(h.onBindingLost);
    expect(talkState.options?.onTokenRevoked).toBe(h.onTokenRevoked);
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


describe("四層版面與一屏不捲（W3b）", () => {
  it("整頁不捲：容器自己裁切，內容再多也不會把主鍵擠出畫面", () => {
    // 規則 2「每個畫面一屏內不捲動——長輩不一定知道要滑」。舊版是 flex 直欄，
    // 回覆一長就把麥克風鍵推下去，而外框還會整頁捲。
    talkState.replyText = "很長的回答。".repeat(200);
    const { container } = renderScreen();
    const root = container.firstElementChild as HTMLElement;
    expect(root.className).toContain("h-full");
    expect(root.className).toContain("overflow-hidden");
  });

  it("字級放大時只有回話內文捲，頁首、角色與主鍵仍固定", () => {
    // 設計稿寫的是 RN 的「fontScale ≥ 1.5 時只有內容層可捲」。網頁沒有 fontScale
    // 這個 API，等價物是使用者調大預設字級／縮放，效果就是文字撐高——所以改由
    // 回話內文自己設上限並捲動，行為與設計意圖一致。
    renderScreen();
    const reply = screen.getByRole("status");
    expect(reply.className).toContain("max-h-[330px]");
    expect(reply.className).toContain("overflow-y-auto");
  });

  it("角色舞台固定在設計稿的 top 140（換算掉狀態列後）", () => {
    // 規則 3：209 × 300 固定，永不縮放或位移。設計稿的 y 以裝置畫面頂端為原點，
    // 而 PhoneFrame 的內容區已扣掉 54px 狀態列。
    renderScreen();
    const stage = screen.getByTestId("bear-stage").parentElement as HTMLElement;
    expect(stage.style.top).toBe("86px");
    expect(stage.className).toContain("z-10");
  });

  it("阿白說話時主鍵縮成 72 並改淡黃底，說完長回 132", () => {
    talkState.avatar = "speaking";
    const h = renderScreen();
    expect(micButton().style.width).toBe("72px");
    expect(micButton().style.backgroundColor).toContain("--talk-idle-pill");
    expect(screen.getByText("等阿白說完，再按這裡")).toBeInTheDocument();

    // 說完回到待機：主鍵長回 132
    talkState.avatar = "idle";
    h.rerender();
    expect(micButton().style.width).toBe("132px");
  });

  it("說話時主鍵仍然按得到——它只是變小，不是停用", () => {
    // 設計稿：「仍是可按的觸控目標」。72px 也高於 48px 下限。
    talkState.avatar = "speaking";
    renderScreen();
    expect(micButton()).not.toBeDisabled();
  });
});

describe("回話卡收合（W3b）", () => {
  it("說完之後收成單行摘要，點一下展開回全文", async () => {
    talkState.avatar = "speaking";
    talkState.replyText = "早上的血壓藥要記得吃，飯後半小時吃比較不傷胃喔。";
    const h = renderScreen();
    expect(screen.getByTestId("reply-card")).toBeInTheDocument();

    // 說完（speaking → idle）才收合
    talkState.avatar = "idle";
    h.rerender();
    const pill = screen.getByTestId("reply-collapsed");
    // 前 12 字（含全形逗號）＋刪節號。
    expect(pill).toHaveTextContent("剛才阿白說：早上的血壓藥要記得吃，飯…");

    await userEvent.click(pill);
    expect(screen.getByTestId("reply-card")).toBeInTheDocument();
    expect(screen.queryByTestId("reply-collapsed")).not.toBeInTheDocument();
  });

  it("新回覆一抵達就展開——不等整段合成完", () => {
    // ⚠️ 分段播放的延遲優化（伺服器只先合成第一句就送出）是為了讓長輩不用等
    // 5–8 秒。卡片若等整段會把這個優化整個吃掉。這裡以「replyText 一變就展開」
    // 表達那個時機：第一段抵達時 replyText 就已經更新。
    talkState.avatar = "speaking";
    talkState.replyText = "第一句話。";
    const h = renderScreen();
    talkState.avatar = "idle";
    h.rerender();
    expect(screen.getByTestId("reply-collapsed")).toBeInTheDocument();

    talkState.replyText = "下一輪的第一段。";
    talkState.avatar = "speaking";
    h.rerender();
    expect(screen.getByTestId("reply-card")).toBeInTheDocument();
  });
});


describe("之前聊過的：入口與寫入（W4）", () => {
  it("頁首左側有 60dp 圓鈕進「之前聊過的」", async () => {
    const h = renderScreen();
    const entry = screen.getByRole("button", { name: "之前聊過的" });
    expect(entry.className).toContain("size-[var(--size-elder-round-button)]");
    await userEvent.click(entry);
    expect(h.onOpenHistory).toHaveBeenCalledOnce();
  });

  it("一輪講完就寫進當日紀錄", async () => {
    talkState.avatar = "speaking";
    talkState.transcript = "今天天氣真好";
    talkState.replyText = "是啊，要不要出去走走？";
    const h = renderScreen();
    // 說完（speaking → idle）才算一輪結束
    talkState.avatar = "idle";
    h.rerender();
    await waitFor(async () =>
      expect((await loadToday()).map((t) => [t.said, t.reply])).toEqual([
        ["今天天氣真好", "是啊，要不要出去走走？"],
      ]),
    );
  });

  it("後端沒送逐字稿時不寫——不可偽造長輩沒講過的話", async () => {
    // 舊版後端不送 `transcript`。寧可少一則紀錄，也不要在「您說」那一行編一句話。
    talkState.avatar = "speaking";
    talkState.transcript = "";
    talkState.replyText = "是啊。";
    const h = renderScreen();
    talkState.avatar = "idle";
    h.rerender();
    await waitFor(() => expect(screen.getByTestId("reply-collapsed")).toBeInTheDocument());
    expect(await loadToday()).toEqual([]);
  });

  it("同一輪重繪很多次也只寫一筆", async () => {
    talkState.avatar = "speaking";
    talkState.transcript = "今天天氣真好";
    talkState.replyText = "是啊。";
    const h = renderScreen();
    talkState.avatar = "idle";
    h.rerender();
    await waitFor(async () => expect(await loadToday()).toHaveLength(1));
    h.rerender();
    h.rerender();
    expect(await loadToday()).toHaveLength(1);
  });
});
