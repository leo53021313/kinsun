/**
 * 家屬錄音的狀態機。
 *
 * 這裡守的三件事，錯了都不會噴錯、只會靜默壞掉：8 秒門檻（錄太短會讓 CosyVoice
 * 的輸出長度亂跳）、blob 網址要回收（不回收就一直佔記憶體）、卸載時要放掉麥克風
 * （不放的話分頁的錄音指示燈一直亮著，家屬會以為在偷聽）。
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useVoiceRecording } from "./useVoiceRecording";

function fakeRecorder(options: { bytes?: Uint8Array | null; started?: boolean } = {}) {
  const { bytes = new Uint8Array([1, 2, 3]), started = true } = options;
  return {
    start: vi.fn().mockResolvedValue(started),
    stop: vi.fn().mockResolvedValue(bytes === null ? null : bytes.buffer),
    isRecording: vi.fn().mockReturnValue(false),
    mimeType: vi.fn().mockReturnValue("audio/webm"),
  };
}

/** 可控時鐘：錄音長度是用時間戳算的，不是數 tick。 */
function clockAt(values: number[]) {
  let index = 0;
  return () => values[Math.min(index++, values.length - 1)];
}

function deps(recorder: ReturnType<typeof fakeRecorder>, nowValues: number[]) {
  return {
    createRecorderFn: () => recorder,
    now: clockAt(nowValues),
    createObjectUrl: vi.fn().mockReturnValue("blob:preview"),
    revokeObjectUrl: vi.fn(),
  };
}

afterEach(() => vi.restoreAllMocks());

describe("useVoiceRecording", () => {
  it("錄滿 8 秒才讓送出", async () => {
    const recorder = fakeRecorder();
    const d = deps(recorder, [0, 8000]);
    const { result } = renderHook(() => useVoiceRecording(d));
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.stop();
    });
    await waitFor(() => expect(result.current.status).toBe("recorded"));
    expect(result.current.durationMs).toBe(8000);
    expect(result.current.isLongEnough).toBe(true);
  });

  it("差 0.1 秒也不讓送——門檻是硬的，不是提示", async () => {
    const recorder = fakeRecorder();
    const d = deps(recorder, [0, 7900]);
    const { result } = renderHook(() => useVoiceRecording(d));
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.stop();
    });
    await waitFor(() => expect(result.current.status).toBe("recorded"));
    expect(result.current.isLongEnough).toBe(false);
  });

  it("重錄會回收前一段的 blob 網址", async () => {
    const recorder = fakeRecorder();
    const d = deps(recorder, [0, 9000, 9000, 20000]);
    const { result } = renderHook(() => useVoiceRecording(d));
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.stop();
    });
    await waitFor(() => expect(result.current.previewUri).toBe("blob:preview"));
    await act(async () => {
      await result.current.start();
    });
    expect(d.revokeObjectUrl).toHaveBeenCalledWith("blob:preview");
  });

  it("錄音中卸載要放掉麥克風，不留殘留指示燈", async () => {
    const recorder = fakeRecorder();
    const d = deps(recorder, [0, 9000]);
    const { result, unmount } = renderHook(() => useVoiceRecording(d));
    await act(async () => {
      await result.current.start();
    });
    unmount();
    expect(recorder.stop).toHaveBeenCalled();
  });

  it("重繪不可以把正在進行的錄音停掉（iPhone 實測：按停止沒反應）", async () => {
    // ⚠️ 這條刻意**每次 render 都給一個新的 deps 物件**，因為那正是正式路徑的行為：
    // `VoiceProfileScreen` 呼叫 `useVoiceRecording()` 不帶參數，而
    // `deps: VoiceRecordingDeps = {}` 是預設參數——每次 render 都重建，
    // 四個預設實作因此都是新的函式實體。
    //
    // 本檔其他測試都把 `d` 建好一次重複用，識別碼是穩定的，所以「卸載清理」
    // 那個 effect 不會重跑——**測試替身把缺陷遮住了**。真實症狀：家屬按下開始
    // 錄音後計時器在跳，但錄音器早在第一次重繪就被自己的 cleanup 停掉、
    // ref 也清成 null，於是按「停止」時 `stop()` 直接 early return，
    // 畫面永遠停在錄音中。
    const recorder = fakeRecorder();
    const clock = clockAt([0, 9000]);
    const { result, rerender } = renderHook(() =>
      useVoiceRecording({
        createRecorderFn: () => recorder,
        now: clock,
        createObjectUrl: () => "blob:preview",
        revokeObjectUrl: () => {},
      }),
    );
    await act(async () => {
      await result.current.start();
    });

    rerender(); // 計時器每 100ms 就會造成一次重繪

    expect(recorder.stop).not.toHaveBeenCalled();
    await act(async () => {
      await result.current.stop();
    });
    await waitFor(() => expect(result.current.status).toBe("recorded"));
  });

  it("麥克風拿不到時不進錄音狀態", async () => {
    const recorder = fakeRecorder({ started: false });
    const d = deps(recorder, [0]);
    const { result } = renderHook(() => useVoiceRecording(d));
    let ok = true;
    await act(async () => {
      ok = await result.current.start();
    });
    expect(ok).toBe(false);
    expect(result.current.status).toBe("idle");
  });

  it("錄到空音檔視為沒錄到，不讓送出", async () => {
    // 軌道被系統搶走（來電、藍牙耳機被拔）時會走到這裡。長度可能夠，但沒有東西
    // 可以送——不擋的話會送出一個空 body，後端回 400 missing_audio。
    const recorder = fakeRecorder({ bytes: null });
    const d = deps(recorder, [0, 9000]);
    const { result } = renderHook(() => useVoiceRecording(d));
    await act(async () => {
      await result.current.start();
    });
    await act(async () => {
      await result.current.stop();
    });
    await waitFor(() => expect(result.current.status).toBe("recorded"));
    expect(result.current.audio).toBeNull();
    expect(result.current.isLongEnough).toBe(false);
  });
});
