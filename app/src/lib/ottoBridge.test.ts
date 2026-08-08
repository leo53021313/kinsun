import {
  createOttoSyncCommand,
  OTTO_BRIDGE_VERSION,
  parseOttoRendererEvent,
  type OttoVisualState,
} from "./ottoBridge";
import type { TalkVisualState } from "./talkPresentation";

describe("Otto WebView bridge", () => {
  test("非說話態只送五態，不把上一段文字帶進下一態", () => {
    expect(
      createOttoSyncCommand(3, "thinking", {
        key: "old",
        text: "上一段",
        durationMs: 1234,
      }),
    ).toEqual({ version: OTTO_BRIDGE_VERSION, type: "sync", sequence: 3, state: "thinking" });
  });

  test("說話態帶文字、音檔時長與選填情緒", () => {
    expect(
      createOttoSyncCommand(4, "speaking", {
        key: "turn-1:reply",
        text: "我在這裡陪您。",
        durationMs: 2450.4,
        emotion: "touched",
      }),
    ).toEqual({
      version: OTTO_BRIDGE_VERSION,
      type: "sync",
      sequence: 4,
      state: "speaking",
      text: "我在這裡陪您。",
      durationMs: 2450,
      emotion: "touched",
    });
  });

  test("限制橋接文字長度且把時長收斂在安全範圍", () => {
    const command = createOttoSyncCommand(5, "speaking", {
      key: "long",
      text: "字".repeat(600),
      durationMs: -10,
    });
    expect(command.text).toHaveLength(500);
    expect(command.durationMs).toBe(0);
    expect(
      createOttoSyncCommand(6, "speaking", {
        key: "too-long",
        text: "測試",
        durationMs: 999_999,
      }).durationMs,
    ).toBe(120_000);
  });

  test("只接受已知版本與事件型別", () => {
    expect(parseOttoRendererEvent('{"version":1,"type":"ready"}')).toEqual({
      version: OTTO_BRIDGE_VERSION,
      type: "ready",
    });
    expect(parseOttoRendererEvent('{"version":2,"type":"ready"}')).toBeNull();
    expect(parseOttoRendererEvent('{"version":1,"type":"anything"}')).toBeNull();
    expect(parseOttoRendererEvent("not-json")).toBeNull();
  });
});

test("bridge 的狀態聯集與對講機狀態機的五態相容", () => {
  // 編譯期斷言（執行期沒有東西可驗）：`shared/ottoBridge.ts` 刻意不從
  // `talkPresentation` 匯入型別——那支是接手指示第 11 條點名不准動的狀態機檔案，
  // 而 shared 也不該反向依賴任何一端。代價是同一組五個名稱寫了兩份，這條斷言
  // 就是防它們漂：任一邊多一個或改名，這裡會編譯失敗。
  const toBridge: OttoVisualState = "speaking" as TalkVisualState;
  const toStateMachine: TalkVisualState = "speaking" as OttoVisualState;
  expect([toBridge, toStateMachine]).toEqual(["speaking", "speaking"]);
});
