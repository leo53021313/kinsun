/** 瀏覽器錄音。用假的 MediaRecorder 與 getUserMedia，測試完全不碰真麥克風。 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { createRecorder } from "./recorder";

class FakeMediaRecorder {
  static lastInstance: FakeMediaRecorder | null = null;
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  state = "inactive";

  constructor(public stream: unknown) {
    FakeMediaRecorder.lastInstance = this;
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2, 3])]) });
    this.onstop?.();
  }
}

function stubBrowser(options: { denied?: boolean } = {}) {
  const stop = vi.fn();
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  vi.stubGlobal("navigator", {
    mediaDevices: {
      getUserMedia: options.denied
        ? vi.fn().mockRejectedValue(new Error("NotAllowedError"))
        : vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
    },
  });
  return { stop };
}

afterEach(() => vi.unstubAllGlobals());

describe("createRecorder", () => {
  it("開始錄音回報成功", async () => {
    stubBrowser();
    const recorder = createRecorder();
    expect(await recorder.start()).toBe(true);
    expect(recorder.isRecording()).toBe(true);
  });

  it("使用者拒絕麥克風時回 false，不擲例外", async () => {
    // 擲出去的話，長輩端整個畫面會白掉——他連「重試」的按鈕都看不到。
    stubBrowser({ denied: true });
    const recorder = createRecorder();
    expect(await recorder.start()).toBe(false);
    expect(recorder.isRecording()).toBe(false);
  });

  it("停止後拿得到錄到的位元組", async () => {
    stubBrowser();
    const recorder = createRecorder();
    await recorder.start();
    const bytes = await recorder.stop();
    expect(bytes).toBeInstanceOf(ArrayBuffer);
    expect(bytes!.byteLength).toBe(3);
  });

  it("停止時關掉麥克風軌道，不讓瀏覽器一直亮著錄音指示燈", async () => {
    const { stop } = stubBrowser();
    const recorder = createRecorder();
    await recorder.start();
    await recorder.stop();
    expect(stop).toHaveBeenCalled();
  });

  it("沒在錄音時停止回 null，不當掉", async () => {
    stubBrowser();
    expect(await createRecorder().stop()).toBeNull();
  });

  it("MediaRecorder 建立失敗時仍要關掉已取得的麥克風軌道，不留殘留指示燈", async () => {
    // 找到的問題（brief 未涵蓋）：getUserMedia 成功後，若 `new MediaRecorder(stream)`
    // 這一行才失敗（例如瀏覽器不支援某些設定），brief 原始的 catch 區塊只把
    // `stream` 參考設成 null，從沒呼叫 `track.stop()`——麥克風其實還開著、
    // 指示燈仍亮，跟本工項要防的第一種錯一模一樣。
    const stop = vi.fn();
    vi.stubGlobal(
      "MediaRecorder",
      class {
        constructor() {
          throw new Error("此設定不受支援");
        }
      },
    );
    vi.stubGlobal("navigator", {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop }] }),
      },
    });
    const recorder = createRecorder();
    expect(await recorder.start()).toBe(false);
    expect(stop).toHaveBeenCalled();
  });
});
