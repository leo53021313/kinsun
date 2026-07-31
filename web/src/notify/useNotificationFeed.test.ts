/**
 * 通知輪詢。
 *
 * 純函式 pickNewItems 是這裡的核心判斷，單獨測；hook 的部分只測「會不會重複
 * 顯示同一則」與「換人時要不要重來」，那兩件事錯了在展示現場最明顯。
 *
 * ⚠️ 「第一輪輪詢＝建立基準，不播任何東西」是這裡每條 hook 測試共用的前提
 * （見 `useNotificationFeed.ts` 檔頭「brief 缺陷 2」）：審查抓到第一版修正
 * 把基準設成已讀水位，結果掛載時只要水位不是 0，就會把水位之後累積的既存
 * 通知整批當成新的補播出來——跟 brief 說的「一進站滑進十幾張橫幅」是同一個
 * 失敗，只是換了個時機發生。這裡刻意分兩輪測：第一輪只確認「不播」，第二輪
 * 才餵真正新的資料確認「會播」，兩件事分開釘住。
 *
 * ⚠️ 另外補了幾類這份 spec 已經咬過人的測試：
 * 1. 佇列上限（brief 原始版本沒有上限）；情境刻意是「輪詢期間湧入」而非
 *    「一進站就有」，避免又踩回「補播歷史」那個坑（審查發現：舊版這條測試
 *    的情境正是「已讀水位＋既存 25 則＋第一次輪詢」，等於釘住了錯的那一邊）。
 * 2. `<StrictMode>` 下 state updater 的雙呼叫（審查發現的 Important 2）。
 * 3. 卸載後才回來的輪詢結果不會再更新畫面（手動控制 promise）。
 * 4. `unread` 徽章只讀已讀水位、不因輪詢本身自動歸零，且換人／登出時立刻
 *    歸零（brief 缺陷 1＋審查發現的 Important 3）。
 * 5. 401 與其餘錯誤分開處理（審查發現的 Important 4）。
 * 6. 三條資源釋放路徑（輪詢計時器／分頁可見性監聽器／橫幅自動消失計時器）
 *    卸載後都要清掉（審查發現的 Important 5：這三條先前一條測試都沒有）。
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import type { AppNotification } from "kinsun-shared/types";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api";

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

  it("即使已讀水位不是 0（使用者以前開過提醒列表），掛載時也不會把既存的舊通知當成新的補播出來", async () => {
    // ⚠️ 這條測試釘住審查抓到的 brief 缺陷 2：第一版修正把「第一次不補播歷史」
    // 的基準設成已讀水位，但兩支 NotificationsScreen 開啟時會把水位存成
    // 「當時最新一則」——只要使用者以前開過一次列表、之後有任何新通知累積，
    // 水位就不是 0，掛載時就會把水位之後的全部通知當成新的整批播完。
    saveSeenAt(100, "guardian");
    const backlog = Array.from({ length: 7 }, (_, i) => item(200 + i, `第${i + 1}則`));
    api.guardian.mockResolvedValueOnce(backlog);
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );
    await act(async () => {});
    // 一進站不該滑進任何一張橫幅——即使已讀水位不是 0、即使既存 7 則都比水位新。
    expect(result.current.banner).toBeNull();
  });

  it("不會重複顯示同一則：同一則資料出現在下一輪時不會再排進佇列", async () => {
    api.guardian.mockResolvedValueOnce([item(200)]); // 第一輪：建立基準，不播
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );
    await act(async () => {});
    expect(result.current.banner).toBeNull();

    api.guardian.mockResolvedValueOnce([item(200), item(300, "x")]);
    await act(async () => {
      result.current.reload();
    });
    expect(result.current.banner?.content).toBe("x");
    // 標題走既有品牌字串（brief 原始版本在這裡寫死「金孫」這個裸字串；已改為
    // 讀 strings.gate.brand，值不變，斷言仍寫死字面值——這裡驗證的是「使用者
    // 看到的東西」，不是「元件內部從哪裡取值」）。
    expect(result.current.banner?.title).toBe("金孫");
    act(() => result.current.dismiss());
    expect(result.current.banner).toBeNull();

    // 同一批資料再度出現（後端沒有新東西）：不該重播。
    api.guardian.mockResolvedValueOnce([item(200), item(300, "x")]);
    await act(async () => {
      result.current.reload();
    });
    expect(result.current.banner).toBeNull();
    expect(api.guardian).toHaveBeenCalledTimes(3);
  });

  it("一次輪詢抓到兩則新的，播放順序是最舊的先", async () => {
    api.guardian.mockResolvedValueOnce([item(100)]); // 第一輪：建立基準
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );
    await act(async () => {});
    expect(result.current.banner).toBeNull();

    api.guardian.mockResolvedValueOnce([item(300, "b"), item(200, "a")]);
    await act(async () => {
      result.current.reload();
    });
    expect(result.current.banner?.content).toBe("a");
    act(() => result.current.dismiss());
    expect(result.current.banner?.content).toBe("b");
  });

  it("連續兩則橫幅：第二則有自己完整的 3.5 秒倒數，不會被第一則的計時器提前關掉", async () => {
    api.guardian.mockResolvedValueOnce([item(100)]); // 第一輪：建立基準
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );
    await act(async () => {});
    expect(result.current.banner).toBeNull();

    api.guardian.mockResolvedValueOnce([item(300, "b"), item(200, "a")]);
    await act(async () => {
      result.current.reload();
    });
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

  it("<StrictMode> 下一次輪詢抓到兩則新的，兩則都會播到（不會被 dev 下 state updater 的雙呼叫吃掉中間那則）", async () => {
    // ⚠️ 這條測試釘住審查發現的 Important 2：`setBanner((current) => current ??
    // queue.current.shift() ?? null)` 在 updater 函式裡呼叫有副作用的
    // `queue.current.shift()`。`<StrictMode>`（`main.tsx` 已掛）在開發模式下
    // 會把 updater 函式呼叫兩次以偵測不純的邏輯，`shift()` 因此被呼叫兩次、
    // 佇列裡排在中間的那一則被無聲丟掉。已改為只把值傳給 `setBanner`（讀
    // `bannerRef` 判斷要不要 shift，且只呼叫一次）。
    api.guardian.mockResolvedValueOnce([item(100)]); // 第一輪：建立基準
    const { result } = renderHook(
      () => useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
      { wrapper: StrictMode },
    );
    await act(async () => {});
    expect(result.current.banner).toBeNull();

    api.guardian.mockResolvedValueOnce([item(300, "b"), item(200, "a")]);
    await act(async () => {
      result.current.reload();
    });
    // 沒有 StrictMode 保護的話，這裡會直接是 "b"（"a" 被雙呼叫吃掉）。
    expect(result.current.banner?.content).toBe("a");
    act(() => result.current.dismiss());
    expect(result.current.banner?.content).toBe("b");
  });

  it("佇列有上限，滿了時捨舊留新（情境是輪詢期間一次湧入 25 則，不是一進站就有既存資料）", async () => {
    api.guardian.mockResolvedValueOnce([item(100)]); // 第一輪：建立基準，不播
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );
    await act(async () => {});
    expect(result.current.banner).toBeNull();

    const many = Array.from({ length: 25 }, (_, i) => item(200 + i, `n${i}`));
    api.guardian.mockResolvedValueOnce(many);
    await act(async () => {
      result.current.reload();
    });

    const seen: string[] = [];
    while (result.current.banner !== null) {
      seen.push(result.current.banner.content);
      act(() => result.current.dismiss());
    }

    // 25 則一次湧入，只留得住上限 20 則——最舊的 5 則（n0～n4）被捨棄，
    // 留下的是 n5～n24，依「最舊的先播」的順序播出。
    expect(seen).toHaveLength(20);
    expect(seen[0]).toBe("n5");
    expect(seen.at(-1)).toBe("n24");
  });

  it("換人（token 換掉）時，上一位的橫幅與佇列不會帶到新的人身上", async () => {
    api.guardian.mockResolvedValueOnce([item(100)]); // tokA 第一輪：建立基準
    const { result, rerender } = renderHook(
      (props: { token: string }) =>
        useNotificationFeed({ audience: "guardian", token: props.token, intervalMs: 60_000 }),
      { initialProps: { token: "tokA" } },
    );
    await act(async () => {});
    expect(result.current.banner).toBeNull();

    api.guardian.mockResolvedValueOnce([item(100), item(300, "來自 A")]);
    await act(async () => {
      result.current.reload();
    });
    await waitFor(() => expect(result.current.banner?.content).toBe("來自 A"));

    api.guardian.mockResolvedValueOnce([item(500)]); // 換人自動觸發 tokB 第一輪：建立基準
    rerender({ token: "tokB" });

    // 一換人立刻清空，不等下一輪輪詢才發現。
    expect(result.current.banner).toBeNull();

    await act(async () => {}); // 讓換人自動觸發的 tokB 第一輪跑完
    expect(result.current.banner).toBeNull();
    expect(api.guardian).toHaveBeenLastCalledWith("tokB");

    api.guardian.mockResolvedValueOnce([item(500), item(700, "來自 B")]);
    await act(async () => {
      result.current.reload();
    });
    await waitFor(() => expect(result.current.banner?.content).toBe("來自 B"));
  });

  it("換人時，前一位使用者「還在飛」的輪詢結果晚到，不會污染新使用者的橫幅", async () => {
    // ⚠️ 這條測試釘住比「換人立刻清空」更隱蔽的一種時序：`mountedRef` 只擋得住
    // 「元件真的卸載了」，換人不會讓元件卸載，只會讓 `poll` 換一顆新的閉包——
    // 上一位使用者那顆還在飛的呼叫不受影響，resolve 之後一樣會照跑。用手動
    // 控制的 promise 讓 tokA 的那次輪詢刻意慢到，等 tokB 已經換上、也拉過一輪
    // 資料之後才回來，驗證這批遲到的舊資料不會被當成新橫幅塞進去。
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

  it('長輩身分（audience="elder"）走長輩端點，不會誤打家屬端點', async () => {
    api.elder.mockResolvedValueOnce([item(100)]); // 第一輪：建立基準
    const { result } = renderHook(() =>
      useNotificationFeed({ audience: "elder", token: "tok", intervalMs: 60_000 }),
    );
    await act(async () => {});
    expect(result.current.banner).toBeNull();

    api.elder.mockResolvedValueOnce([item(100), item(300, "吃藥囉")]);
    await act(async () => {
      result.current.reload();
    });
    await waitFor(() => expect(result.current.banner?.content).toBe("吃藥囉"));
    expect(api.elder).toHaveBeenCalledWith("tok");
    expect(api.guardian).not.toHaveBeenCalled();
  });

  it("unread 徽章只讀已讀水位，不會因為輪詢本身跑過就自動歸零", async () => {
    // ⚠️ 這條測試釘住 brief 缺陷 1：brief 原始版本每輪都把「已讀水位」推進到
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

  it("登出（token 換成空字串）時 unread 與橫幅立刻歸零，不會留著上一位的未讀數", async () => {
    // ⚠️ 這條測試釘住審查發現的 Important 3：換人的「render 期間比對」原本只
    // 歸零 banner，unread 沒有——登出後 poll() 因 !token 直接 return，unread
    // 會停在上一位使用者的數字上，直到下一位使用者的第一輪輪詢才會被蓋掉。
    saveSeenAt(100, "guardian");
    api.guardian.mockResolvedValue([item(300), item(200)]);
    const { result, rerender } = renderHook(
      (props: { token: string }) =>
        useNotificationFeed({ audience: "guardian", token: props.token, intervalMs: 60_000 }),
      { initialProps: { token: "tok" } },
    );
    await waitFor(() => expect(result.current.unread).toBe(2));

    rerender({ token: "" });
    expect(result.current.unread).toBe(0);
    expect(result.current.banner).toBeNull();
  });

  it("401（token 被撤銷）時呼叫 onTokenRevoked，不同於一般網路錯誤的靜默", async () => {
    // ⚠️ 這條測試釘住審查發現的 Important 4：web 裡其餘六支會打網路的模組
    // 全部接了 session/useSignOutOnAuthError.ts，本 hook 原本是唯一的例外。
    const onTokenRevoked = vi.fn();
    api.guardian.mockRejectedValueOnce(new ApiError(401, "invalid_token"));
    renderHook(() =>
      useNotificationFeed({
        audience: "guardian",
        token: "tok",
        intervalMs: 60_000,
        onTokenRevoked,
      }),
    );
    await waitFor(() => expect(onTokenRevoked).toHaveBeenCalledOnce());
  });

  it("一般網路錯誤（非 401）不會誤觸發 onTokenRevoked，仍完全靜默", async () => {
    const onTokenRevoked = vi.fn();
    api.guardian.mockRejectedValueOnce(new Error("network"));
    renderHook(() =>
      useNotificationFeed({
        audience: "guardian",
        token: "tok",
        intervalMs: 60_000,
        onTokenRevoked,
      }),
    );
    await act(async () => {});
    expect(onTokenRevoked).not.toHaveBeenCalled();
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

  it("元件卸載後才回來的輪詢結果不會拋出例外或印出警告（不是驗證 state 真的沒被寫——React 18 起呼叫已卸載元件的 setState 本身已是安全的無操作，mountedRef 的價值在別處，見程式碼註解）", async () => {
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

  it("卸載會清掉輪詢計時器，之後不會再打任何請求", async () => {
    // ⚠️ 審查發現的 Important 5：這三條資源釋放路徑（本條、下兩條）先前
    // 一條測試都沒有——把對應的 clearInterval／removeEventListener／
    // clearTimeout 個別拿掉，19/19 都還是全綠。
    //
    // ⚠️ 只斷言「呼叫次數不再增加」不夠精確：`tick()` 內部還有一層 `alive`
    // 旗標會擋掉呼叫，即使拿掉 `clearInterval(timer)` 本身，`alive=false`
    // 一樣能讓呼叫次數維持不變（實測驗證過，兩者疊在一起會讓這條斷言看不出
    // 差異）。改用 `vi.getTimerCount()` 直接驗證計時器本身真的被清掉，才是
    // 這條測試名稱要釘住的那一行。
    api.guardian.mockResolvedValue([]);
    const { unmount } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 1000 }),
    );
    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(1));
    const timersBeforeUnmount = vi.getTimerCount();
    unmount();
    expect(vi.getTimerCount()).toBeLessThan(timersBeforeUnmount);

    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    // 卸載後十輪的份都不該再打。
    expect(api.guardian).toHaveBeenCalledTimes(1);
  });

  it("卸載會移除分頁可見性監聽器，之後觸發 visibilitychange 不會再打請求", async () => {
    // ⚠️ 同上一條的理由：只斷言「呼叫次數不再增加」不夠精確，`onVisible` 內部
    // 也有 `alive` 擋著，即使拿掉 `removeEventListener` 本身，呼叫次數斷言
    // 一樣不會變（實測驗證過）。改用 spy 直接驗證 `removeEventListener` 真的
    // 被呼叫、且是這支 hook 掛上去的那個監聽器（同一個函式參考）。
    api.guardian.mockResolvedValue([]);
    const removeSpy = vi.spyOn(document, "removeEventListener");
    const { unmount } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );
    await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(1));
    unmount();
    expect(removeSpy).toHaveBeenCalledWith("visibilitychange", expect.any(Function));

    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(api.guardian).toHaveBeenCalledTimes(1);
    removeSpy.mockRestore();
  });

  it("卸載時若正顯示著橫幅，會清掉它的自動消失計時器", async () => {
    api.guardian.mockResolvedValueOnce([item(100)]); // 第一輪：建立基準
    const { result, unmount } = renderHook(() =>
      useNotificationFeed({ audience: "guardian", token: "tok", intervalMs: 60_000 }),
    );
    await act(async () => {});

    api.guardian.mockResolvedValueOnce([item(100), item(300, "x")]);
    await act(async () => {
      result.current.reload();
    });
    await waitFor(() => expect(result.current.banner?.content).toBe("x"));

    const clearSpy = vi.spyOn(global, "clearTimeout");
    unmount();
    expect(clearSpy).toHaveBeenCalled();
    clearSpy.mockRestore();
  });

  it("瀏覽器分頁切到背景時暫停輪詢，切回前景立刻補一次", async () => {
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

  /**
   * `visible`（P4 Task 4 接線）：窄螢幕頁籤模式下被 CSS 蓋住的那一欄，同一種坑
   * `elder/useTalk.ts` 的麥克風／相機已經修過四次（見檔頭「接線狀態 1」）。
   */
  describe("visible", () => {
    it("visible 為 false 時完全不會打請求，即使經過多輪間隔", async () => {
      api.guardian.mockResolvedValue([]);
      renderHook(() =>
        useNotificationFeed({
          audience: "guardian",
          token: "tok",
          intervalMs: 1000,
          visible: false,
        }),
      );
      await act(async () => {
        vi.advanceTimersByTime(5000);
      });
      expect(api.guardian).not.toHaveBeenCalled();
    });

    it("visible 從 false 變 true 時立刻補一次輪詢，不必等下一個間隔", async () => {
      api.guardian.mockResolvedValue([]);
      const { rerender } = renderHook(
        (props: { visible: boolean }) =>
          useNotificationFeed({
            audience: "guardian",
            token: "tok",
            intervalMs: 60_000,
            visible: props.visible,
          }),
        { initialProps: { visible: false } },
      );
      await act(async () => {
        vi.advanceTimersByTime(5000);
      });
      expect(api.guardian).not.toHaveBeenCalled();

      rerender({ visible: true });
      await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(1));
    });

    it("visible 變回 false 之後，連分頁切回前景這種本來會補打一次的觸發也不再打", async () => {
      // ⚠️ 只驗證「呼叫次數不再增加」還不夠精確（同本檔卸載那幾條測試的理由）：
      // 這裡改用「切去背景又切回前景」當探針——若 `visible` 沒有真的擋住整條
      // effect（含監聽器註冊），visibilitychange 一樣會補打一輪。
      api.guardian.mockResolvedValue([]);
      const { rerender } = renderHook(
        (props: { visible: boolean }) =>
          useNotificationFeed({
            audience: "guardian",
            token: "tok",
            intervalMs: 60_000,
            visible: props.visible,
          }),
        { initialProps: { visible: true } },
      );
      await waitFor(() => expect(api.guardian).toHaveBeenCalledTimes(1));

      rerender({ visible: false });
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      expect(api.guardian).toHaveBeenCalledTimes(1);
    });
  });
});
