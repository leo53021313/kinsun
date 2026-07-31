/**
 * 通知輪詢。
 *
 * 純函式 pickNewItems 是這裡的核心判斷，單獨測；hook 的部分只測「會不會重複
 * 顯示同一則」與「換人時要不要重來」，那兩件事錯了在展示現場最明顯。
 *
 * ⚠️ 另外補了三類這份 spec 已經咬過人的測試：
 * 1. 佇列上限（brief 原始版本沒有上限，見 useNotificationFeed.ts 檔頭說明）。
 * 2. 卸載後才回來的輪詢結果不會再更新畫面（手動控制 promise，不用
 *    `mockResolvedValue` 一次到位——那種寫法看不到「還在飛」的中間狀態）。
 * 3. `unread` 徽章只讀已讀水位、不因輪詢本身自動歸零（brief 原始版本這裡的
 *    `unread` 可以證明恆為 0，是本輪修正的缺陷；見同檔案說明）。
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import type { AppNotification } from "kinsun-shared/types";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveSeenAt } from "./seen";
import { pickNewItems, useNotificationFeed } from "./useNotificationFeed";

function item(at: number, content = "x"): AppNotification {
  return { content, created_at: at };
}

describe("pickNewItems", () => {
  it("只挑比水位新的", () => {
    expect(pickNewItems([item(300), item(200), item(100)], 150)).toEqual([item(300), item(200)]);
  });

  it("水位剛好等於某一則時，那一則不算新的", () => {
    expect(pickNewItems([item(200)], 200)).toEqual([]);
  });

  it("第一次載入時（水位 0）不把整批舊通知當成新的", () => {
    // ⚠️ 這是展示現場最尷尬的失敗：一進站就滑進十幾張橫幅、蓋滿整個手機。
    // 第一次載入的用途是「記下目前的水位」，不是「補播歷史」。
    expect(pickNewItems([item(300), item(200)], 0)).toEqual([]);
  });

  it("沒有任何通知時回空陣列", () => {
    expect(pickNewItems([], 100)).toEqual([]);
  });

  it("後端回的順序若不是最新在前也要正確", () => {
    // 端點的排序是後端的實作細節，不該讓這裡的正確性依賴它。
    expect(pickNewItems([item(100), item(300), item(200)], 150)).toEqual([item(300), item(200)]);
  });
});

/**
 * 假通知端點：`vi.hoisted` 讓 mock 工廠拿得到同一份參考（同 `stage/StagePage.test.tsx`
 * 既有慣例）。兩個角色各自一支 `vi.fn()`，呼叫端自己決定要 `mockResolvedValue`
 * （一路回同一批）或 `mockResolvedValueOnce`（逐輪換一批）或手動控制的
 * `mockImplementation`（測「還在飛的那一次」）。
 */
const api = vi.hoisted(() => ({ guardian: vi.fn(), elder: vi.fn() }));

vi.mock("@/guardian/api", () => ({
  listNotifications: (token: string) => api.guardian(token),
}));
vi.mock("@/elder/api", () => ({
  listElderNotifications: (token: string) => api.elder(token),
}));

/** 可控制的假分頁可見性（真正的 `document.hidden` 在瀏覽器裡是唯讀的）。 */
function stubHidden(hidden: boolean) {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
}

beforeEach(() => {
  localStorage.clear();
  api.guardian.mockReset();
  api.elder.mockReset();
  stubHidden(false);
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  stubHidden(false);
});

describe("useNotificationFeed", () => {
  it("token 是空字串（尚未登入）時不會打任何請求", async () => {
    renderHook(() => useNotificationFeed({ audience: "guardian", token: "", intervalMs: 1000 }));
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    expect(api.guardian).not.toHaveBeenCalled();
  });

  it("不會重複顯示同一則：下一輪抓到同一批舊資料時不會再排進佇列", async () => {
    saveSeenAt(100, "guardian");
    api.guardian.mockResolvedValue([item(300)]);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 1000 }),
    );

    await waitFor(() => expect(result.current.banner?.content).toBe("x"));
    // 標題走既有品牌字串（brief 原始版本在這裡寫死「金孫」這個裸字串；已改為
    // 讀 strings.gate.brand，值不變，斷言仍寫死字面值——這裡驗證的是「使用者
    // 看到的東西」，不是「元件內部從哪裡取值」）。
    expect(result.current.banner?.title).toBe("金孫");

    act(() => result.current.dismiss());
    expect(result.current.banner).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(2));
    expect(result.current.banner).toBeNull();
  });

  it("一次輪詢抓到兩則新的，播放順序是最舊的先", async () => {
    saveSeenAt(100, "guardian");
    api.guardian.mockResolvedValueOnce([item(300, "b"), item(200, "a")]);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );

    await waitFor(() => expect(result.current.banner?.content).toBe("a"));
    act(() => result.current.dismiss());
    expect(result.current.banner?.content).toBe("b");
  });

  it("連續兩則橫幅：第二則有自己完整的 3.5 秒倒數，不會被第一則的計時器提前關掉", async () => {
    // ⚠️ 這條測試刻意不用 `waitFor`：`waitFor` 內部用真實時間反覆輪詢，
    // 搭配 `shouldAdvanceTime: true` 會讓假時鐘跟著多走掉幾毫秒——在後面
    // 「剛好 3499ms 還沒到」這種毫秒級的斷言上，這點漂移就足夠讓測試打結
    // 誤判成計時器提前關掉。改用 `act(async () => {})` 只 flush 微工作
    // （目前這一輪已解出的 promise），不引入額外的真實時間流逝。
    saveSeenAt(100, "guardian");
    api.guardian.mockResolvedValueOnce([item(300, "b"), item(200, "a")]);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );

    await act(async () => {});
    expect(result.current.banner?.content).toBe("a");

    await act(async () => {
      vi.advanceTimersByTime(3499);
    });
    expect(result.current.banner?.content).toBe("a");

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.banner?.content).toBe("b");

    // 換到第二則之後，倒數要從頭算：若被第一則殘留的計時器影響，這裡會提早消失。
    await act(async () => {
      vi.advanceTimersByTime(3499);
    });
    expect(result.current.banner?.content).toBe("b");

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current.banner).toBeNull();
  });

  it("佇列有上限，滿了時捨舊留新", async () => {
    saveSeenAt(100, "guardian");
    const many = Array.from({ length: 25 }, (_, i) => item(200 + i, `n${i}`));
    api.guardian.mockResolvedValueOnce(many);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );

    await waitFor(() => expect(result.current.banner).not.toBeNull());

    const seen: string[] = [];
    while (result.current.banner !== null) {
      seen.push(result.current.banner.content);
      act(() => result.current.dismiss());
    }

    // 25 則新資料湧入，只留得住上限 20 則——最舊的 5 則（n0～n4）被捨棄，
    // 留下的是 n5～n24，依「最舊的先播」的順序播出。
    expect(seen).toHaveLength(20);
    expect(seen[0]).toBe("n5");
    expect(seen.at(-1)).toBe("n24");
  });

  it("換人（token 換掉）時，上一位的橫幅與佇列不會帶到新的人身上", async () => {
    saveSeenAt(100, "guardian");
    api.guardian.mockResolvedValueOnce([item(300, "來自 A")]);
    const { result, rerender } = renderHook(
      (props: { token: string }) =>
        useNotificationFeed({ audience: "guardian", token: props.token, intervalMs: 60_000 }),
      { initialProps: { token: "tokA" } },
    );

    await waitFor(() => expect(result.current.banner?.content).toBe("來自 A"));

    api.guardian.mockResolvedValueOnce([item(500, "來自 B")]);
    rerender({ token: "tokB" });

    // 一換人立刻清空，不等下一輪輪詢才發現。
    expect(result.current.banner).toBeNull();

    await waitFor(() => expect(result.current.banner?.content).toBe("來自 B"));
    expect(api.guardian).toHaveBeenLastCalledWith("tokB");
  });

  it("長輩身分（audience=\"elder\"）走長輩端點，不會誤打家屬端點", async () => {
    saveSeenAt(100, "elder");
    api.elder.mockResolvedValue([item(300, "吃藥囉")]);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "elder", token: "tok", intervalMs: 60_000 }),
    );

    await waitFor(() => expect(result.current.banner?.content).toBe("吃藥囉"));
    expect(api.elder).toHaveBeenCalledWith("tok");
    expect(api.guardian).not.toHaveBeenCalled();
  });

  it("unread 徽章只讀已讀水位，不會因為輪詢本身跑過就自動歸零", async () => {
    // ⚠️ 這條測試釘住本輪修正的缺陷：brief 原始版本每輪都把「已讀水位」推進到
    // 這一批資料的最新一則再存回去，緊接著又用剛存的值去算 unread——可以證明
    // 那樣算出來的 unread 恆為 0。這裡要驗證的是：使用者還沒開過提醒列表之前，
    // 就算輪詢本身跑了好幾輪，未讀數也不能自己掉下來。
    saveSeenAt(100, "guardian");
    api.guardian.mockResolvedValue([item(300), item(200)]);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 1000 }),
    );

    await waitFor(() => expect(result.current.unread).toBe(2));

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(2));
    expect(result.current.unread).toBe(2);

    // 模擬使用者真的打開了提醒列表（那支畫面自己會呼叫 saveSeenAt）。
    saveSeenAt(300, "guardian");
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(result.current.unread).toBe(0));
  });

  it("輪詢失敗時完全靜默，不影響下一輪繼續嘗試", async () => {
    api.guardian.mockRejectedValueOnce(new Error("network"));
    api.guardian.mockResolvedValueOnce([]);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 1000 }),
    );

    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(1));
    expect(result.current.banner).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(2));
  });

  it("元件卸載後才回來的輪詢結果，不會再更新畫面（不噴錯、不假裝完成）", async () => {
    saveSeenAt(100, "guardian");
    let resolvePoll: ((items: AppNotification[]) => void) | null = null;
    api.guardian.mockImplementation(
      () =>
        new Promise<AppNotification[]>((resolve) => {
          resolvePoll = resolve;
        }),
    );
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);

    const { unmount } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );
    unmount();

    await act(async () => {
      resolvePoll?.([item(300)]);
    });

    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });

  it("瀏覽器分頁切到背景時暫停輪詢，切回前景立刻補一次", async () => {
    saveSeenAt(100, "guardian");
    api.guardian.mockResolvedValue([]);
    renderHook(() => useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 1000 }));

    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(1));

    stubHidden(true);
    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    // 分頁在背景的這五秒（原本間隔該再打 5 次），一次都不該打。
    expect(api.guardian).toHaveBeenCalledTimes(1);

    stubHidden(false);
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(2));
  });

  it("reload() 手動觸發立刻重新拉一次，不必等下一次輪詢", async () => {
    api.guardian.mockResolvedValue([]);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );

    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(1));
    await act(async () => {
      result.current.reload();
    });
    expect(api.guardian).toHaveBeenCalledTimes(2);
  });

  it("reloadSignal 一變就立刻重新拉一次", async () => {
    api.guardian.mockResolvedValue([]);
    const { rerender } = renderHook(
      (props: { reloadSignal: number }) =>
        useNotificationFeed({
          audience: "guardian",
          token: "tok",
          intervalMs: 60_000,
          reloadSignal: props.reloadSignal,
        }),
      { initialProps: { reloadSignal: 0 } },
    );

    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(1));
    rerender({ reloadSignal: 1 });
    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(2));
  });

  it("換人時，前一位使用者「還在飛」的輪詢結果晚到，不會污染新使用者的橫幅", async () => {
    // ⚠️ 這條測試釘住比「換人立刻清空」更隱蔽的一種時序：`mountedRef` 只擋得住
    // 「元件真的卸載了」，換人不會讓元件卸載，只會讓 `poll` 換一顆新的閉包——
    // 上一位使用者那顆還在飛的呼叫不受影響，resolve 之後一樣會照跑。用手動
    // 控制的 promise 讓 tokA 的那次輪詢刻意慢到，等 tokB 已經換上、也拉過一輪
    // 資料之後才回來，驗證這批遲到的舊資料不會被當成新橫幅塞進去。
    saveSeenAt(100, "guardian");
    let resolveTokA: ((items: AppNotification[]) => void) | null = null;
    api.guardian.mockImplementationOnce(
      () =>
        new Promise<AppNotification[]>((resolve) => {
          resolveTokA = resolve;
        }),
    );
    const { result, rerender } = renderHook(
      (props: { token: string }) =>
        useNotificationFeed({ audience: "guardian", token: props.token, intervalMs: 60_000 }),
      { initialProps: { token: "tokA" } },
    );

    api.guardian.mockResolvedValueOnce([]);
    rerender({ token: "tokB" });
    await act(async () => {});
    expect(result.current.banner).toBeNull();

    // tokA 那個遲到的回應現在才回來，帶著一則看起來很新的資料。
    await act(async () => {
      resolveTokA?.([item(999, "遲到的 A")]);
    });

    // 不該把這則塞進佇列／顯示出來——它屬於已經換掉的那個人。
    expect(result.current.banner).toBeNull();
  });
});
