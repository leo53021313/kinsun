/** 進場判定：哪些狀態能按「開始使用」。
 *
 * 這是純函式，測起來便宜；而它決定的是使用者的第一個動作能不能做，
 * 判錯的兩種代價不對稱——誤放進去會看到壞掉的產品，誤擋在外只是多等十秒。
 */

import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { canEnter, useDemoStatus } from "./useDemoStatus";

const state = (overall: string) => ({
  status: { overall, components: {} },
  unreachable: false,
});

describe("canEnter", () => {
  it("完全正常時可以進入", () => {
    expect(canEnter(state("available"))).toBe(true);
  });

  it("部分受限時仍可進入", () => {
    // 語音合成掛掉還看得到字幕，那是可用的降級，不該把人擋在門外。
    expect(canEnter(state("degraded"))).toBe(true);
  });

  it("啟動中不可進入", () => {
    // 再等幾秒就好，讓他進去只會得到「按了沒反應」。
    expect(canEnter(state("starting"))).toBe(false);
  });

  it("停機不可進入", () => {
    expect(canEnter(state("down"))).toBe(false);
  });

  it("還沒問到結果時不可進入", () => {
    expect(canEnter({ status: null, unreachable: false })).toBe(false);
  });

  it("連不上後端時不可進入", () => {
    expect(canEnter({ status: null, unreachable: true })).toBe(false);
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useDemoStatus", () => {
  it("問到結果後把整體與分項一起帶回來", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 200,
        json: async () => ({
          success: true,
          data: { overall: "available", components: { asr: "ok" } },
          error: null,
          meta: null,
        }),
      }),
    );
    const { result } = renderHook(() => useDemoStatus());
    await waitFor(() => expect(result.current.status?.overall).toBe("available"));
    expect(result.current.unreachable).toBe(false);
  });

  it("打不到後端時回報連不上，而不是回報服務停機", async () => {
    // ⚠️ 這兩件事在畫面上是不同的一句話：前者要去看伺服器有沒有開，後者要去看是
    // 哪個服務掛了。混成同一句會讓人查錯方向。
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
    const { result } = renderHook(() => useDemoStatus());
    await waitFor(() => expect(result.current.unreachable).toBe(true));
    expect(result.current.status).toBeNull();
  });
});
