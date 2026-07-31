/**
 * iOS Safari 音訊解鎖：只在第一次呼叫時真的觸發播放，之後呼叫是無操作。
 *
 * ⚠️ brief 的 Test 清單只列了 recorder.test.ts／playback.test.ts，沒有替
 * `audioUnlock.ts` 排測試——但這支檔案有真實的邏輯（模組層級的一次性旗標、
 * `resetAudioUnlockForTest` 的復位），且離「解鎖時機」這個本工項最容易出錯的
 * 地方最近，故補上這支測試檔（AGENTS.md／testing.md 的最低覆蓋率與 TDD 要求）。
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { resetAudioUnlockForTest, unlockAudio } from "./audioUnlock";

afterEach(() => resetAudioUnlockForTest());

describe("unlockAudio", () => {
  it("第一次呼叫會用無聲音檔觸發一次播放，且順序是先 replace 再 play", () => {
    // 順序是這支檔案唯一承重的語意：iOS 只認得「使用者手勢的同步呼叫堆疊內
    // 播放」，若順序顛倒成先 play() 後 replace()，等於是對一顆還沒指定來源
    // 的播放器喊播放，解不了鎖。單獨斷言呼叫參數／次數擋不住把兩行對調。
    const order: string[] = [];
    const replace = vi.fn(() => order.push("replace"));
    const play = vi.fn(() => order.push("play"));
    unlockAudio({ replace, play });
    expect(replace).toHaveBeenCalledWith({ uri: "/demo/silent.wav" });
    expect(play).toHaveBeenCalledTimes(1);
    expect(order).toEqual(["replace", "play"]);
  });

  it("解鎖過一次之後，之後呼叫不再重播無聲音檔", () => {
    // 只解鎖一次即可：重複播放無聲音檔沒有任何好處，還可能打斷正在播的回覆。
    unlockAudio({ replace: vi.fn(), play: vi.fn() });
    const second = { replace: vi.fn(), play: vi.fn() };
    unlockAudio(second);
    expect(second.replace).not.toHaveBeenCalled();
    expect(second.play).not.toHaveBeenCalled();
  });

  it("resetAudioUnlockForTest 之後可以再解鎖一次", () => {
    unlockAudio({ replace: vi.fn(), play: vi.fn() });
    resetAudioUnlockForTest();
    const after = { replace: vi.fn(), play: vi.fn() };
    unlockAudio(after);
    expect(after.play).toHaveBeenCalledTimes(1);
  });
});
