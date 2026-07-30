import { strings } from "@/lib/strings";
import {
  getTalkPresentation,
  getTalkSocketFrameArrivalState,
  getTalkSocketPlaybackCompletionState,
} from "@/lib/talkPresentation";

describe("getTalkPresentation", () => {
  it("待機時顯示可開始說話", () => {
    expect(getTalkPresentation("idle", null)).toEqual({
      statusLabel: strings.talk.status.idle,
      actionLabel: strings.talk.actions.start,
    });
  });

  it.each([
    ["pressing", strings.talk.actions.listening],
    ["tap", strings.talk.actions.tapToSend],
    ["hold", strings.talk.actions.releaseToSend],
  ] as const)("聆聽模式 %s 顯示正確操作提示", (mode, actionLabel) => {
    expect(getTalkPresentation("listening", mode)).toEqual({
      statusLabel: strings.talk.status.listening,
      actionLabel,
    });
  });

  it.each([
    ["thinking", strings.talk.status.thinking, strings.talk.actions.thinking],
    ["speaking", strings.talk.status.speaking, strings.talk.actions.speaking],
    ["error", strings.talk.status.error, strings.talk.actions.retry],
  ] as const)("狀態 %s 顯示正確狀態與操作文案", (state, statusLabel, actionLabel) => {
    expect(getTalkPresentation(state, null)).toEqual({ statusLabel, actionLabel });
  });
});

describe("getTalkSocketPlaybackCompletionState", () => {
  it("安撫語音播完後仍顯示思考中，直到正式回覆抵達", () => {
    expect(getTalkSocketPlaybackCompletionState("ack", false)).toBe("thinking");
  });

  it("單段正式回覆播完後回到待機", () => {
    expect(getTalkSocketPlaybackCompletionState("reply", false)).toBe("idle");
  });

  it("正式回覆仍有續播分段時保留目前的說話狀態", () => {
    expect(getTalkSocketPlaybackCompletionState("reply", true)).toBeNull();
  });
});

describe("getTalkSocketFrameArrivalState", () => {
  it("帶語音的訊框交給播放佇列決定狀態", () => {
    expect(getTalkSocketFrameArrivalState("reply", true)).toBeNull();
  });

  it("沒有語音的安撫訊框仍維持思考中", () => {
    expect(getTalkSocketFrameArrivalState("ack", false)).toBe("thinking");
  });

  it("只有文字的正式回覆直接回到待機", () => {
    expect(getTalkSocketFrameArrivalState("reply", false)).toBe("idle");
  });
});
