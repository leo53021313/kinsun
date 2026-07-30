/** 進場判定：哪些狀態能按「開始使用」。
 *
 * 這是純函式，測起來便宜；而它決定的是使用者的第一個動作能不能做，
 * 判錯的兩種代價不對稱——誤放進去會看到壞掉的產品，誤擋在外只是多等十秒。
 */

import { describe, expect, it } from "vitest";

import { canEnter } from "./useDemoStatus";

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
