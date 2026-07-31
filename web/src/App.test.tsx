/** 路由與階段轉換。 */

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";
import { TEAR_DURATION_MS } from "./stage/TearTransition";
import { strings } from "./strings";

/**
 * 渲染計數探針：`StagePage` 有沒有被 `memo` 擋下來，從外面看不出結果差異
 * （畫面長得一樣），所以借用它一定會渲染到的葉節點 `PhoneFrame` 來計數。
 * `StagePage` 若真的被 `memo` 擋下（bail out），React 連子樹都不會重新呼叫，
 * 這裡的計數就不會動；若沒被擋下，兩張 `PhoneFrame`（長輩／家屬）每次都會
 * 重新呼叫一次，計數必定往上跳。
 */
let phoneFrameRenderCount = 0;

vi.mock("./stage/PhoneFrame", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./stage/PhoneFrame")>();
  return {
    ...actual,
    PhoneFrame: (props: Parameters<typeof actual.PhoneFrame>[0]) => {
      phoneFrameRenderCount += 1;
      return actual.PhoneFrame(props);
    },
  };
});

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

  it("舞台網址帶尾斜線時仍是舞台，不是開場頁", async () => {
    // ⚠️ 後端的單頁應用回退（_SpaStaticFiles）對 /demo/stage 與 /demo/stage/
    // 兩者都回 200 html——使用者貼網址給別人時多打一個斜線很常見。onStage 若用
    // 嚴格相等比對 pathname，尾斜線版本就不算「在舞台」，畫面會停在開場頁。
    mockAvailable();
    window.history.pushState({}, "", "/demo/stage/");
    render(<App />);
    expect(await screen.findByRole("region", { name: "長輩的手機" })).toBeInTheDocument();
    // ⚠️ 不可再用「開始使用」按鈕的有無來判斷「不是開場頁」：P3 Task 7 接上
    // `ElderApp` 之後，長輩配對畫面（`BindScreen`）自己也有一顆文字相同的
    // 「開始使用」按鈕（`strings.elderBind.start`，與 `strings.gate.start`
    // 恰好同名但語意無關），這條斷言從此對兩顆按鈕都會命中、不再能拿來分辨
    // 「在開場頁」還是「在舞台上」。改認 GatePage 專屬、不會被誤認的文字
    // （品牌標語，舞台上的畫面不會出現這句話）。
    expect(screen.queryByText(strings.gate.slogan)).not.toBeInTheDocument();
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

  it("輪詢造成 Demo 重繪時，舞台不會跟著重繪", async () => {
    // ⚠️ 站上舞台後 useDemoStatus 仍每十秒輪詢一次（見 App.tsx 註解：使用者按上一頁
    // 回開場時要看到新的狀態）。每次輪詢回來都是 setState 一個新物件，Demo 因此
    // 重繪；StagePage 若沒有 memo，會跟著整棵重繪——這對現在的佔位元件無感，但
    // P2／P3 接上表單與對講機之後，就是長輩正在講話的那棵樹每十秒被無條件重繪一次。
    // 用一個渲染計數探針（見檔案開頭的 PhoneFrame mock）驗證：舞台掛好之後，
    // 輪詢重繪不該讓 PhoneFrame 被重新呼叫。
    // shouldAdvanceTime：讓 findByRole 內部用來輪詢的 setTimeout 仍能隨著真實時間
    // 前進，否則假時鐘會連它一起卡住，測試會逾時而不是給出真正有辨別力的失敗。
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { fetchMock, settleAll } = deferredStatusFetch();
    window.history.pushState({}, "", "/demo/stage");
    render(<App />);

    await act(async () => {
      settleAll();
    });
    await screen.findByRole("region", { name: "長輩的手機" });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const rendersAfterMount = phoneFrameRenderCount;
    expect(rendersAfterMount).toBeGreaterThan(0);

    // 推進到下一輪輪詢，並讓它回應——這就是「Demo 因輪詢重繪」的那一下。
    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    await act(async () => {
      settleAll();
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    expect(phoneFrameRenderCount).toBe(rendersAfterMount);

    vi.useRealTimers();
  });
});
