/** useLoadable：把七頁 admin 重複的「載入 → 成功顯示資料／失敗顯示錯誤」收成一處。 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useLoadable } from "./useLoadable";

describe("useLoadable", () => {
  it("載入成功時回傳資料、error 為 null", async () => {
    const fetcher = vi.fn().mockResolvedValue("阿公");

    const { result } = renderHook(() => useLoadable(fetcher));

    await waitFor(() => expect(result.current.data).toBe("阿公"));
    expect(result.current.error).toBeNull();
  });

  it("載入失敗時 error 預設為 true、data 維持 null", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() => useLoadable(fetcher));

    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.data).toBeNull();
  });

  it("錯誤後重載成功，error 才消失", async () => {
    // ⚠️ 這條正是 PR #56 刻意改變的行為：錯誤橫幅留到成功為止，而非一按重載
    // 就立刻消失。抽成 hook 後，這個語意只有這裡守得住。
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("boom"))
      .mockResolvedValueOnce("阿公");

    const { result } = renderHook(() => useLoadable(fetcher));
    await waitFor(() => expect(result.current.error).toBe(true));

    act(() => result.current.reload());

    await waitFor(() => expect(result.current.data).toBe("阿公"));
    expect(result.current.error).toBeNull();
  });

  it("fetcher 回 null 時不載入（條件未滿足）", async () => {
    // 呼叫端的 elderId 還沒從路由解析出來時，回 null 表示「這輪不載入」。
    const fetcher = vi.fn().mockReturnValue(null);

    const { result } = renderHook(() => useLoadable(fetcher));

    await waitFor(() => expect(fetcher).toHaveBeenCalled());
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("mapError 可把例外譯成自訂錯誤值", async () => {
    // TraceDetailPage 要區分 404「查無此筆」與一般失敗，它的 error 是字串——
    // 錯誤型別必須可由呼叫端決定，不能寫死成 boolean。
    const fetcher = vi.fn().mockRejectedValue({ status: 404 });
    const mapError = (exc: unknown) =>
      (exc as { status?: number })?.status === 404 ? "查無此筆" : "載入失敗";

    const { result } = renderHook(() => useLoadable(fetcher, mapError));

    await waitFor(() => expect(result.current.error).toBe("查無此筆"));
  });

  it("fetcher 換新參考時重新載入", async () => {
    const first = vi.fn().mockResolvedValue("第一次");
    const second = vi.fn().mockResolvedValue("第二次");

    const { result, rerender } = renderHook(({ f }) => useLoadable(f), {
      initialProps: { f: first },
    });
    await waitFor(() => expect(result.current.data).toBe("第一次"));

    rerender({ f: second });

    await waitFor(() => expect(result.current.data).toBe("第二次"));
  });

  it("mapError 換新參考不會觸發重新載入", async () => {
    // mapError 由 hook 內部以 ref 保存，故呼叫端不必 useCallback 包它。
    // 理由與 usePolling 相同：它是每次 render 都可能是新參考的回呼，若列入
    // 相依會讓載入無限重跑。
    const fetcher = vi.fn().mockResolvedValue("阿公");

    const { rerender } = renderHook(({ m }) => useLoadable(fetcher, m), {
      initialProps: { m: () => true },
    });
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));

    rerender({ m: () => true }); // 新參考、同語意

    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
