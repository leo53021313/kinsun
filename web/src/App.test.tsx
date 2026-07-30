/** 路由與階段轉換。 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { TEAR_DURATION_MS } from "./stage/TearTransition";
import { strings } from "./strings";

const STATUS_BODY = {
  status: 200,
  json: async () => ({
    success: true,
    data: { overall: "available", components: { asr: "ok" } },
    error: null,
    meta: null,
  }),
};

function mockAvailable() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(STATUS_BODY));
}

/**
 * 可控的 fetch：由測試決定運營狀態什麼時候回來。
 *
 * ⚠️ **不可以**用「同一個 microtask 就 resolve」的 mock。`userEvent.click` 內部的
 * `act()` 會把待處理的 microtask 全部 flush 掉，於是「撕裂當下重新掛載、狀態歸零」
 * 這個症狀會在同一個 act 裡就被補回來——測試恰好通過，而真實網路上（哪怕只有
 * 幾十毫秒 RTT）使用者會實際看到畫面閃回「正在確認服務狀態…」。
 */
function deferredStatusFetch() {
  const resolvers: (() => void)[] = [];
  const fetchMock = vi.fn(
    () => new Promise((resolve) => resolvers.push(() => resolve(STATUS_BODY))),
  );
  vi.stubGlobal("fetch", fetchMock);
  return {
    fetchMock,
    /** 讓目前所有還吊著的請求一次回來。 */
    settleAll: () => resolvers.splice(0).forEach((resolve) => resolve()),
  };
}

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, "", "/demo/");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("一開始在開場頁", async () => {
    mockAvailable();
    render(<App />);
    expect(await screen.findByRole("button", { name: "開始使用" })).toBeInTheDocument();
  });

  it("按下開始使用後進到雙欄舞台", async () => {
    mockAvailable();
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "開始使用" }));
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "長輩的手機" })).toBeInTheDocument();
    });
  });

  it("直接開舞台網址時不播動畫", async () => {
    mockAvailable();
    window.history.pushState({}, "", "/demo/stage");
    render(<App />);
    expect(await screen.findByRole("region", { name: "長輩的手機" })).toBeInTheDocument();
    expect(screen.queryByTestId("tear-left")).not.toBeInTheDocument();
  });

  it("不認得的網址回開場", async () => {
    // ⚠️ 這條路現在才真的走得到：後端補了單頁應用回退（_SpaStaticFiles）之後，
    // `/demo/隨便打` 拿到的是 index.html 而不是 404，前端得自己把網址導正。
    mockAvailable();
    window.history.pushState({}, "", "/demo/不存在的路徑");
    render(<App />);
    expect(await screen.findByRole("button", { name: "開始使用" })).toBeInTheDocument();
    // basename 與 "/" 接起來是 "/demo"（沒有尾斜線）；伺服器那端 Starlette 的
    // mount 會把 /demo 轉到 /demo/，所以瀏覽器上兩者等價。
    await waitFor(() => expect(window.location.pathname).toBe("/demo"));
  });

  it("動畫期間掛好的舞台，切到 /stage 之後不會被卸載重掛", async () => {
    // ⚠️ 這一條守的是「動畫期間就開始載」這個設計本身。舞台若放在 <Routes> 裡面，
    // navigate("/stage") 會把 <Gate/> 整棵子樹（含那個先掛好的舞台）卸載、再掛一個
    // 全新的——省下的 700 毫秒根本不存在，而且是靜默的：P1 的舞台不發請求所以看
    // 不出來，P2／P3 一接上資料載入就會白等一輪。
    //
    // 用「舞台裡一個有狀態的東西有沒有被重置」來驗：頁籤選到家屬端之後，若舞台
    // 重新掛載，pane 會回到預設的長輩端。
    mockAvailable();
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "開始使用" }));

    const guardianTab = await screen.findByRole("tab", { name: "家屬端" });
    await userEvent.click(guardianTab);
    expect(guardianTab).toHaveAttribute("aria-selected", "true");

    await waitFor(() => expect(window.location.pathname).toBe("/demo/stage"), {
      timeout: TEAR_DURATION_MS + 1_000,
    });
    expect(screen.getByRole("tab", { name: "家屬端" })).toHaveAttribute("aria-selected", "true");
  });

  it("從舞台回到開場時不會立刻重播動畫、把人彈回舞台", async () => {
    // ⚠️ 撕裂旗標現在活在路由之上（以前它住在 <Routes> 底下的 Gate 裡，換路由連
    // 元件一起卸載、旗標自然歸零）。不主動收回來的話，一回到開場就會看到動畫重播，
    // 700 毫秒後被彈回舞台——出不去。
    mockAvailable();
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "開始使用" }));
    await waitFor(() => expect(window.location.pathname).toBe("/demo/stage"), {
      timeout: TEAR_DURATION_MS + 1_000,
    });

    // 模擬瀏覽器的上一頁。
    await act(async () => {
      window.history.pushState({}, "", "/demo/");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });

    expect(await screen.findByRole("button", { name: "開始使用" })).toBeInTheDocument();
    expect(screen.queryByTestId("tear-left")).not.toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, TEAR_DURATION_MS + 50));
    expect(window.location.pathname).toBe("/demo/");
  });

  it("撕裂當下畫面仍是已載入的狀態，不會閃回確認中、按鈕也不會變灰", async () => {
    // ⚠️ 這是整個展示的門面動畫：按下去的那一瞬間畫面若閃回「正在確認服務狀態…」
    // 且按鈕變灰，看的人會以為壞了。成因是 TearTransition 在 active 翻轉時把 children
    // 換到 overlay 底下的兩份副本——React 會卸載活著的 GatePage、掛兩個全新實例，
    // 它們自己的 useDemoStatus 於是從 null 重來（並且各再打一次後端）。
    const { fetchMock, settleAll } = deferredStatusFetch();
    render(<App />);
    expect(screen.getByText(strings.gate.checking)).toBeInTheDocument();

    await act(async () => {
      settleAll();
    });
    const button = screen.getByRole("button", { name: "開始使用" });
    expect(button).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await userEvent.click(button);

    // 撕開的左半就是使用者當下看到的畫面。
    // ⚠️ 用 getByText 而非 getByRole：overlay 掛了 aria-hidden（那兩層是裝飾，
    // 不該被讀螢幕唸兩遍），role 查詢走的是無障礙樹，查不到裡面的東西。
    const left = within(screen.getByTestId("tear-left"));
    expect(left.queryByText(strings.gate.checking)).not.toBeInTheDocument();
    expect(left.getByText(strings.gate.overall.available)).toBeInTheDocument();
    expect(left.getByText(strings.gate.start)).toBeEnabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
