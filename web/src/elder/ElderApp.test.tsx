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

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElderSession } from "@/session/contexts";

import { ElderApp } from "./ElderApp";

/**
 * 最後一次傳給 `useTalk` 的參數。
 *
 * ⚠️ 存下來是為了驗**接線**：`ElderApp` → `TalkScreen` → `useTalk` 這條鏈上少傳
 * 一個 prop，畫面看起來完全正常，壞掉的是麥克風與「被登出之後回不回得去」。
 */
const talkOptions = vi.hoisted(() => ({ current: null as Record<string, unknown> | null }));

vi.mock("./useTalk", () => ({
  useTalk: (options: Record<string, unknown>) => {
    talkOptions.current = options;
    return {
      avatar: "idle",
      replyText: "按住下面的麥克風說話，或按一下開始、說完再按一下",
      micReady: true,
      pressIn: vi.fn(),
      pressOut: vi.fn(),
    };
  },
}));

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function renderSignedIn(props: { visible?: boolean } = {}) {
  localStorage.setItem(
    "kinsun_web_session_elder",
    JSON.stringify({ role: "elder", token: "tok", display_name: "王阿嬤" }),
  );
  return render(
    <ElderSession.Provider>
      <ElderApp visible={props.visible} />
    </ElderSession.Provider>,
  );
}

/** 後端回一則失敗信封（狀態碼由呼叫端指定）。 */
function failureResponse(status: number, code: string, message: string) {
  return {
    status,
    json: async () => ({ success: false, data: null, error: { code, message }, meta: null }),
  };
}

beforeEach(() => {
  localStorage.clear();
  talkOptions.current = null;
});
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

describe("被撤銷的登入", () => {
  /**
   * ⚠️ **全分支審查抓到的 Critical 1**：家屬按下「重新產生長輩綁定碼」之後，後端
   * 先撤 token 再拆綁定，長輩端每一支 API 都回 401。原本長輩端**零個畫面**處理 401
   * ——對講機顯示「金孫沒聽清楚」、提醒列表顯示「載入失敗，請稍後再試」，重新整理
   * 也沒用（token 在 localStorage、初始路由仍是對講機），而家屬手上那組新碼永遠
   * 沒有畫面可以輸入。長輩就此永久卡死在一個看起來很正常的畫面上。
   */
  it("對講機回報 token 被撤銷時，回到配對畫面並告訴長輩下一步", async () => {
    renderSignedIn();
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
    act(() => (talkOptions.current?.onTokenRevoked as () => void)());
    // 回得到配對畫面：新碼有地方可以輸入了。
    expect(await screen.findByLabelText("綁定碼")).toBeInTheDocument();
    // 而且告訴他發生什麼事、下一步做什麼——不是把他丟在一個空白的配對畫面前。
    expect(screen.getByRole("alert")).toHaveTextContent(
      "家人幫您重新設定了，請再掃一次他給的方塊圖，或輸入新的號碼。",
    );
    // 登入狀態也要真的清掉，否則重新整理又會回到那個按不動的對講機畫面。
    expect(localStorage.getItem("kinsun_web_session_elder")).toBeNull();
  });

  it("同意被撤回（403）時講的是「綁定失效」，不是「家人幫您重新設定了」", async () => {
    // 兩者的下一步都是「跟家人拿一組碼」，但成因不同：403 是家屬撤回同意（token
    // 仍有效），家屬手上不會自動有一組新碼。講錯會讓長輩去等一個沒有人在產生的東西。
    renderSignedIn();
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
    act(() => (talkOptions.current?.onBindingLost as () => void)());
    expect(await screen.findByLabelText("綁定碼")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "這台手機的綁定失效了，請家人重新給您一組號碼。",
    );
  });

  it("提醒列表吃到 401 時同樣回到配對畫面", async () => {
    // 長輩不一定先按麥克風——他可能先按鈴鐺看提醒。兩條路都要走得回配對畫面。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(failureResponse(401, "invalid_token", "登入已失效")),
    );
    renderSignedIn();
    await userEvent.click(await screen.findByRole("button", { name: "看金孫的提醒" }));
    expect(await screen.findByLabelText("綁定碼")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "家人幫您重新設定了，請再掃一次他給的方塊圖，或輸入新的號碼。",
    );
  });

  it("重新綁定成功之後，下次自己按登出不會再看到「家人幫您重新設定了」", async () => {
    // ⚠️ 那句話是有時效的：他重綁完、之後自己按登出時再看到它，會以為家人又動了
    // 什麼——而那時根本沒有人動過任何東西。
    renderSignedIn();
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });
    act(() => (talkOptions.current?.onTokenRevoked as () => void)());
    await screen.findByLabelText("綁定碼");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 201,
        json: async () => envelope({ elder_id: "e1", name: "王阿嬤", token: "tok2" }),
      }),
    );
    await userEvent.type(screen.getByLabelText("綁定碼"), "AB12CD");
    await userEvent.click(screen.getByRole("button", { name: "開始使用" }));
    await screen.findByRole("button", { name: "按住說話，或按一下開始、再按一下結束" });

    // 自己按登出（不經過 401）回到配對畫面：這時不該有任何說明文字。
    await userEvent.click(screen.getByRole("button", { name: "登出" }));
    await userEvent.click(screen.getByRole("button", { name: "確定登出" }));
    expect(await screen.findByLabelText("綁定碼")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
