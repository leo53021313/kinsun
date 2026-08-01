/**
 * 對講機的狀態與副作用。
 *
 * 依賴全部以 deps 注入，所以這裡完全不碰麥克風、不開 WebSocket、不打網路。
 * 那不只是為了跑得快——對講機的 bug 幾乎都是**時序**問題（放開比開錄先到、
 * 播放中又開口、上一輪的續拉沒作廢），而時序只有在能精確控制每一步的
 * 環境裡才測得出來。
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api";
import { resetAudioUnlockForTest } from "@/talk/audioUnlock";
import type { MicrophoneProbeResult } from "@/talk/recorder";

import { useTalk } from "./useTalk";

/**
 * 「錄到的那段音檔」的辨識標記。
 *
 * ⚠️ 不用 `expect.any(ArrayBuffer)` 斷言送出的音檔：**空的 ArrayBuffer 也是
 * ArrayBuffer**。實測變異——把送出的音檔換成 `new ArrayBuffer(0)`——那種斷言
 * 照樣全綠，而長輩的錄音一個位元組都不會離開瀏覽器。這與 Task 6「三條 postTurn
 * 都沒斷言 body」是同一個洞，這裡改成比對真正的內容。
 */
const AUDIO_MARK = 0xa7;

function makeRecordedBytes(size: number): ArrayBuffer {
  const bytes = new Uint8Array(size);
  if (size > 0) {
    bytes[0] = AUDIO_MARK;
  }
  return bytes.buffer;
}

/** 斷言這真的是「剛剛錄到的那段音檔」，而不是任何一個 ArrayBuffer。 */
function expectRecordedAudio(value: unknown) {
  expect(value).toBeInstanceOf(ArrayBuffer);
  const bytes = new Uint8Array(value as ArrayBuffer);
  expect(bytes.byteLength).toBe(16);
  expect(bytes[0]).toBe(AUDIO_MARK);
}

/**
 * 可以精確控制「開錄什麼時候完成」的假錄音器工廠。
 *
 * `finishStart()` 是這裡的關鍵：不呼叫它，`start()` 就一直停在未完成——那正是
 * 「放開比開錄先到」那條測試需要的場景。
 *
 * ⚠️ `stop()` 在「沒有在錄音」時是 no-op（不計數、回 null），與真正的
 * `createRecorder().stop()` 語意一致（見 `talk/recorder.ts`：`recorder === null`
 * 時直接回 null）。假的若無條件計數，「切走頁籤時要停止錄音」那條測試就算實作
 * 完全沒有停止錄音也會通過——那正是這份 spec 已經抓到十幾次的「恰好通過」。
 *
 * ⚠️ **`create()` 每次都造一顆新的**，因為正式的 `createRecorder()` 也是——每顆
 * 各自持有自己的 `MediaStream`。這一點不是細節：切走頁籤時的清理會排一個「等開錄
 * 流程跑完再停」的延後停止，那個停止是針對**那一輪的那顆**錄音器。假物件若全域
 * 共用一顆，切回來之後長輩按下的新一輪錄音會被上一輪的延後停止吃掉——實作沒有這
 * 個問題（物件不同），假物件卻會憑空製造一個。這個坑實際發生過，除錯時才發現。
 */
function makeRecorder(
  options: { granted?: boolean; emptyRecording?: boolean; stopThrows?: boolean } = {},
) {
  const granted = options.granted ?? true;
  let resolveStart: ((value: boolean) => void) | null = null;
  const api = {
    started: 0,
    stopped: 0,
    /**
     * 讓**下一次**開錄解出 false（裝置忙、系統把軌道收走），之後恢復正常。
     *
     * ⚠️ 與 `setup({ startFails: true })` 的差別是「這一次」而不是「每一次」：
     * 「開錄失敗那一輪留下來的東西，會不會在**下一輪成功的對話**裡冒出來」這種
     * 跨輪的殘留，在永遠開不起來的錄音器上根本走不到。
     */
    failNextStart: false,
    /** 讓最近一次還沒完成的 `start()` 收工。 */
    finishStart() {
      const ok = api.failNextStart ? false : granted;
      api.failNextStart = false;
      resolveStart?.(ok);
      resolveStart = null;
    },
    create() {
      let recording = false;
      return {
        start() {
          api.started += 1;
          return new Promise<boolean>((resolve) => {
            resolveStart = (value: boolean) => {
              recording = value;
              resolve(value);
            };
          });
        },
        stop() {
          if (!recording) {
            return Promise.resolve<ArrayBuffer | null>(null);
          }
          api.stopped += 1;
          recording = false;
          if (options.stopThrows) {
            // 真的 `recorder.stop()` 內部有 try/finally 與保險逾時，理論上不擲例外
            // ——但「理論上不會」不該拿來當程式碼的依據（`useTalk` 自己的註解就是
            // 這麼寫的）。這個開關讓那條路徑真的走得到。
            return Promise.reject<ArrayBuffer | null>(new Error("stop 爆了"));
          }
          return Promise.resolve<ArrayBuffer | null>(
            makeRecordedBytes(options.emptyRecording ? 0 : 16),
          );
        },
        isRecording: () => recording,
      };
    },
  };
  return api;
}

/**
 * 假播放器工廠。
 *
 * ⚠️ **`create()` 每次都造一顆新的**，因為正式的 `createWebPlayer()` 也是——它每次
 * 都 `new Audio()`。這一點是承重的：iOS 的音訊解鎖**綁在單一 `HTMLMediaElement`
 * 上**（`playback.ts` 自己寫下的前提），換一顆播放器等於沒解鎖。假物件若全域共用
 * 一顆，「切走再切回來之後新播放器有沒有重新解鎖」這件事在測試裡根本觀察不到——
 * 而那正是審查抓到的 Critical 1（iPhone 切一次頁籤之後再也聽不到聲音）。
 *
 * 監聽者依實例各自持有（真播放器也是），`finish()` 只對最近建立的那一顆生效。
 */
function makePlayer() {
  let latestListeners = new Set<(status: { didJustFinish: boolean }) => void>();
  const api = {
    played: [] as string[],
    paused: 0,
    disposed: 0,
    created: 0,
    /** 模擬「這一則播完了」（對最近建立的那一顆播放器）。 */
    finish() {
      latestListeners.forEach((listener) => listener({ didJustFinish: true }));
    },
    create() {
      api.created += 1;
      const listeners = new Set<(status: { didJustFinish: boolean }) => void>();
      latestListeners = listeners;
      return {
        addListener(
          _event: "playbackStatusUpdate",
          listener: (s: { didJustFinish: boolean }) => void,
        ) {
          listeners.add(listener);
          return { remove: () => listeners.delete(listener) };
        },
        replace(source: { uri: string }) {
          api.played.push(source.uri);
        },
        play() {},
        pause() {
          api.paused += 1;
        },
        dispose() {
          api.disposed += 1;
        },
        element: null as unknown as HTMLAudioElement,
      };
    },
  };
  return api;
}

/**
 * 可以由測試決定何時「連上」、並直接餵下行訊框的假 WebSocket。
 *
 * ⚠️ **送出的東西依實例各自持有**（`api.sent` 讀的永遠是**最新那條連線**的）：真正的
 * `WebSocket` 在切走／重連之後是另一個物件，往舊的那條送出去不會抵達對方。假物件
 * 若讓所有實例共用一份 `sent`，「切頁籤之後切回來，送出去的是新連線」這件事在測試裡
 * 就恆真——與 Task 8 挖出的假播放器（全域共用一顆，iOS 解鎖「換一顆等於沒解鎖」因此
 * 觀察不到）是同一種不忠實。目前還沒有測試依賴它，先讓假物件對得起真實的形狀。
 */
function makeSocket() {
  const api = {
    socket: null as FakeWebSocket | null,
    /** 最新那條連線送出去的東西。 */
    get sent(): (string | ArrayBuffer)[] {
      return api.socket?.sent ?? [];
    },
    factory(url: string) {
      api.socket = new FakeWebSocket(url);
      return api.socket as unknown as WebSocket;
    },
    open() {
      api.socket?.onopen?.(new Event("open"));
    },
    emit(frame: unknown) {
      api.socket?.onmessage?.({ data: JSON.stringify(frame) } as MessageEvent);
    },
  };
  return api;
}

class FakeWebSocket {
  binaryType = "blob";
  readyState = 1;
  closed = 0;
  /** 這**一條連線**（不是這一次測試）送出去的東西。 */
  sent: (string | ArrayBuffer)[] = [];
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor(public url: string) {}
  send(payload: string | ArrayBuffer) {
    this.sent.push(payload);
  }
  close() {
    this.closed += 1;
    this.readyState = 3;
  }
}

const REPLY = {
  text: "今天天氣很好",
  audio_url: "https://cdn.example/a.m4a",
  duration_ms: 1200,
  chunk_count: 1,
  reply_digest: "d1",
};

function setup(
  overrides: Partial<{
    granted: boolean;
    micProbe: MicrophoneProbeResult;
    emptyRecording: boolean;
    /** 進畫面時探測得到麥克風，但真的按下去要開錄時失敗（裝置忙、軌道被收走）。 */
    startFails: boolean;
    /** `recorder.stop()` 擲例外（走 `stopAndSend` 的 catch，驗 `finally` 的順序）。 */
    stopThrows: boolean;
  }> = {},
) {
  const granted = overrides.granted ?? true;
  const harness = {
    recorder: makeRecorder({
      granted: granted && !overrides.startFails,
      emptyRecording: overrides.emptyRecording,
      stopThrows: overrides.stopThrows,
    }),
    player: makePlayer(),
    socket: makeSocket(),
    postTurn: vi.fn().mockResolvedValue(REPLY),
    currentPlace: vi.fn().mockResolvedValue(null),
    revokeQueuedReplyAudio: vi.fn(),
    revokeReplyAudio: vi.fn(),
    onBindingLost: vi.fn(),
    onTokenRevoked: vi.fn(),
  };
  const view = renderHook(
    (props: { visible: boolean }) =>
      useTalk({
        token: "tok",
        visible: props.visible,
        onBindingLost: harness.onBindingLost,
        onTokenRevoked: harness.onTokenRevoked,
        deps: {
          createRecorder: () => harness.recorder.create(),
          createPlayer: () => harness.player.create(),
          createSocket: harness.socket.factory,
          postTurn: harness.postTurn,
          currentPlace: harness.currentPlace,
          revokeQueuedReplyAudio: harness.revokeQueuedReplyAudio,
          revokeReplyAudio: harness.revokeReplyAudio,
          probeMicrophone: vi
            .fn()
            .mockResolvedValue(overrides.micProbe ?? (granted ? "granted" : "denied")),
        },
      }),
    { initialProps: { visible: true } },
  );
  return { ...harness, view };
}

/**
 * 模擬「長輩碰了畫面上某個東西」（鈴鐺、登出、另一欄、空白處都算）。
 *
 * ⚠️ 事件直接派到 `window`：`useTalk` 的解鎖監聽器掛在 `window` 的 capture 階段，
 * 而事件的 target 就是 window 時，capture 與 bubble 兩種監聽器都會在 at-target
 * 階段被呼叫。刻意不用 `PointerEvent`——jsdom 對它的支援視版本而定，而這條監聽器
 * 一個欄位都沒讀。
 */
function tapAnywhere() {
  window.dispatchEvent(new Event("pointerdown"));
}

/** 走完一次「按住說話」：按下 → 開錄完成 → 達長按門檻 → 放開。 */
async function holdAndRelease(h: ReturnType<typeof setup>) {
  act(() => h.view.result.current.pressIn());
  act(() => h.recorder.finishStart());
  await act(async () => {
    vi.advanceTimersByTime(600);
  });
  await act(async () => {
    h.view.result.current.pressOut();
  });
}

beforeEach(() => {
  // ⚠️ `unlockAudio` 的「已解鎖」旗標住在模組層，跨測試會殘留：不歸零的話，
  // 第一條呼叫 pressIn 的測試會把後面每一條的解鎖都吃掉，測試結果因此與執行
  // 順序有關。
  resetAudioUnlockForTest();
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => vi.useRealTimers());

describe("按住說話", () => {
  it("按下去開始錄音，畫面顯示在聽", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));
    expect(h.recorder.started).toBe(1);
  });

  it("放開之後送出，畫面顯示在想", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    await holdAndRelease(h);
    expect(h.recorder.stopped).toBe(1);
    expect(h.view.result.current.avatar).toBe("thinking");
    // 音檔走長連線，不是 POST——而且送出去的必須是剛剛錄到的那段位元組。
    const sentAudio = h.socket.sent.find((item) => item instanceof ArrayBuffer);
    expectRecordedAudio(sentAudio);
    expect(h.postTurn).not.toHaveBeenCalled();
  });

  it("沒有更早的觸碰時，按下麥克風仍然要補上解鎖", async () => {
    // ⚠️ iOS Safari 不允許在沒有使用者手勢的情況下播放音訊，而金孫的回覆是在
    // 訊框抵達時才播——那已經脫離手勢鏈。不做的話症狀是「iPhone 上只看得到字、
    // 聽不到聲音，桌機一切正常」。
    // ⚠️ 解鎖的主要時機已提早（見「iOS 音訊解鎖」那一組），這裡守的是補漏那一
    // 條：`pressIn` 的呼叫刪掉之後，「播放中插嘴」那條路徑會留下一顆從未解鎖的
    // 播放器。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    act(() => h.view.result.current.pressIn());
    // 寫死字面值而非讀常數：這是與後端靜態檔位置（`web/public/silent.wav` →
    // `/demo/silent.wav`）之間的契約，兩邊各自改到才算改對。
    expect(h.player.played[0]).toBe("/demo/silent.wav");
  });
});

describe("iOS 音訊解鎖", () => {
  it("進畫面後第一次碰到畫面就先解鎖，不等長輩按麥克風", async () => {
    // ✅ **專案裁決 2026-08-01（選項 B）**：`docs/dev/17` 記載 2026-07-18 的真實
    // 故障——App 端在開錄的同一個手勢裡先播提示音，WebKit 的音訊工作階段被播放
    // 搶走，iPhone 錄到的音檔**全數 ≤0.72 秒且近無聲**。解鎖若只掛在麥克風鍵上，
    // 形狀與那次故障相同，故提早到「這顆播放器誕生之後的第一個觸碰」。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    act(() => tapAnywhere());
    expect(h.player.played).toContain("/demo/silent.wav");
    // ⚠️ 這一條的重點是「**不是**麥克風那一下解的鎖」：錄音器一次都沒被開過。
    expect(h.recorder.started).toBe(0);
  });

  it("金孫講到一半時碰畫面，不可以把他的話切斷去解鎖", async () => {
    // ⚠️ 這是把解鎖搬到 `window` 上之後**新出現**的風險：`unlockAudio` 會
    // `replace()` 播放器的來源，正在播的那一則會當場斷掉、blob URL 被回收。
    // 長輩播放中按一下鈴鐺想看提醒，金孫的話就沒了——這條監聽器自己製造的故障。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1" });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/a.m4a"));

    act(() => tapAnywhere());
    expect(h.player.played).not.toContain("/demo/silent.wav");

    // ⚠️ 而且不可以就此放棄：播完之後的下一次觸碰仍然要解鎖，否則「一進畫面就
    // 先聽到一則提醒回覆」的長輩，這顆播放器一輩子解不了鎖。
    await act(async () => {
      h.player.finish();
    });
    act(() => tapAnywhere());
    expect(h.player.played).toContain("/demo/silent.wav");
  });

  it("這一欄被切走之後，晚到的觸碰不可以碰已經丟掉的播放器", async () => {
    // 監聽器綁的是**這一顆**播放器。cleanup 不移除的話，切走之後（播放器已
    // `dispose()`）的任何一次觸碰都還會對它 `replace()`／`play()`，而且每切一次
    // 就多留一條——一場展示下來累積十幾條監聽器對著十幾顆死掉的播放器。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.view.rerender({ visible: false });
    await waitFor(() => expect(h.player.disposed).toBe(1));

    act(() => tapAnywhere());
    expect(h.player.played).not.toContain("/demo/silent.wav");
  });
});

describe("短按切換", () => {
  it("未達長按門檻就放開時維持聆聽，並提示說完再按一下", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await act(async () => {
      h.view.result.current.pressOut();
    });
    expect(h.view.result.current.avatar).toBe("listening");
    expect(h.view.result.current.replyText).toContain("說完再按一下");
    expect(h.recorder.stopped).toBe(0);
  });

  it("按住不到半秒就放開仍算短按——長按門檻不可以縮到 0", async () => {
    // 上界有人守著（門檻拉長到 5 秒會讓十一條變紅），下界原本沒有：把 LONG_PRESS_MS
    // 改成 0，「未達長按門檻」那條仍然綠——因為它按下去之後立刻放開，計時器根本
    // 沒有機會跑。真實的長輩手指沒那麼快，按個三四百毫秒是常態，那時門檻若是 0
    // 就會被判成「按住說話」而直接送出，短按切換模式等於不存在。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await act(async () => {
      vi.advanceTimersByTime(400);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    expect(h.recorder.stopped).toBe(0);
    expect(h.view.result.current.avatar).toBe("listening");
  });

  it("再按一下就送出", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {
      h.view.result.current.pressIn();
    });
    expect(h.recorder.stopped).toBe(1);
  });
});

describe("時序", () => {
  it("放開比開錄完成先到時不可漏掉停止", async () => {
    // ⚠️ App 版的實際 bug（2026-07-25 修）：先前用 avatar state 守門，而 pressOut
    // 常比重繪先到、讀到過期值，於是「聆聽中」殘留、二次按壓把音檔洗掉。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    // 還沒 finishStart 就放開（且已達長按門檻）
    await act(async () => {
      vi.advanceTimersByTime(600);
      h.view.result.current.pressOut();
    });
    // 開錄這時才完成——停止必須等它，然後真的執行
    await act(async () => {
      h.recorder.finishStart();
    });
    await waitFor(() => expect(h.recorder.stopped).toBe(1));
  });

  it("開錄時暫停正在播的，排隊中那幾則等他講完再補播", async () => {
    // ⚠️ 不暫停的話金孫自己的聲音會被錄進去。
    //
    // ✅ **裁決 2026-08-01 改回補播**（推翻 2026-07-31 的「一律丟棄」）：排隊中還沒
    // 播到的那幾則**不再丟掉**，收音期間先收下來，`stopAndSend` 收音真的結束之後
    // 才放回佇列。本條同時守住兩件事：收音期間不可以放音（那是 P3 Task 8 Critical 2，
    // 金孫的聲音會被錄進 ASR），以及講完之後那一則要真的播得出來。
    //
    // ⚠️ 讓佇列裡**真的有東西在排隊**才有鑑別力（原版只 emit 一則、立刻被播掉，
    // 是審查抓到的第十八個假測試）：後端的 ack→reply 兩段式正好會連續送兩則。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({
      type: "ack",
      turn_id: "t1",
      text: "好，我幫您查一下喔",
      audio_url: "https://cdn.example/ack.m4a",
      duration_ms: 30_000,
    });
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1", audio_url: "https://cdn.example/second.m4a" });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/ack.m4a"));
    // 第二則還在排隊（一次只播一則）。
    expect(h.player.played).not.toContain("https://cdn.example/second.m4a");

    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.player.paused).toBeGreaterThan(0));
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    // 收音期間從頭到尾都不可以播出來。
    expect(h.player.played).not.toContain("https://cdn.example/second.m4a");
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});
    // 講完了：排隊中那一則補播出來，長輩不會因為插嘴就永遠聽不到那個答案。
    expect(h.player.played).toContain("https://cdn.example/second.m4a");
  });

  it("長輩正按著麥克風時，晚到的回覆不可以放音——金孫的聲音會被錄進去", async () => {
    // ⚠️ **審查抓到的 Critical 2**。後端 `ws.py` 是明文設計的 ack→reply 兩段式：
    // 先回一句「好，我幫您查一下喔」，答案好了再送第二則。長輩不耐煩、播完 ack
    // 就按住麥克風講第二句，而第一輪的真正答案 5～10 秒後才回來——原本那一則會
    // 在他還按著麥克風講話時放出來，ASR 收到的是長輩的話混著金孫的聲音。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({
      type: "ack",
      turn_id: "t1",
      text: "好，我幫您查一下喔",
      audio_url: "https://cdn.example/ack.m4a",
      duration_ms: 900,
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/ack.m4a"));

    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));

    // 第一輪的真正答案這時才回來——長輩還按著麥克風。
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      text: "附近有 205 跟 622",
      audio_url: "https://cdn.example/answer.m4a",
    });
    await act(async () => {});
    expect(h.player.played).not.toContain("https://cdn.example/answer.m4a");
    // 也不可以把畫面從「金孫在聽…」搶走——長輩還在講話。
    expect(h.view.result.current.avatar).toBe("listening");
    expect(h.view.result.current.replyText).toBe("金孫在聽…");
  });

  it("收音期間抵達的回覆等他講完之後補播，音檔不可以被回收掉", async () => {
    // ✅ **專案裁決 2026-08-01**（推翻 2026-07-31 的「一律丟棄」）：**插嘴照樣要能
    // 打斷，但前一題的答案不要丟掉**——長輩問「我的藥要吃幾顆」，等不及又問了別的，
    // 丟掉的話那一題就永遠沒有答案。補播的語意是「等他講完、送出之後才播」，收音
    // 期間仍然一個音都不可以放（P3 Task 8 Critical 2：金孫的聲音會被錄進 ASR）。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));

    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      text: "附近有 205 跟 622",
      audio_url: "https://cdn.example/answer.m4a",
    });
    await act(async () => {});
    expect(h.player.played).not.toContain("https://cdn.example/answer.m4a");
    // ⚠️ **這一則的音檔不可以被回收**：等一下還要播。`revokeQueuedReplyAudio` 是
    // 「除了這一則以外全部回收」，在補播的世界裡呼叫它就是把要補播的那幾則毀掉，
    // 而症狀是「補播時播放器拿到失效的 blob URL、靜靜地沒有聲音」——查起來很久。
    expect(h.revokeQueuedReplyAudio).not.toHaveBeenCalled();
    expect(h.revokeReplyAudio).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});
    // 講完了才播——這一刻錄音已經真的停下來（`recorder.stop()` 回來了）。
    expect(h.player.played).toContain("https://cdn.example/answer.m4a");
    // 字幕跟著真的播出來的那一則走，長輩看得到這句話在回答什麼。
    expect(h.view.result.current.replyText).toBe("附近有 205 跟 622");
  });

  it("補播照抵達順序來，而且排在新問題的答案前面", async () => {
    // ⚠️ 順序是刻意的（FIFO）：舊答案**現在就在手上**，新問題的答案還要等後端跑
    // 五到十秒——先播舊的正好把那段空白填掉。反過來排的話長輩會先面對一段沉默、
    // 再聽到一句更久以前的答案，那才真的像金孫在自言自語。
    // ⚠️ 收下來的那幾則彼此之間也要照抵達順序（安撫話在答案前面，倒過來播是
    // 「附近有 205 跟 622……好，我幫您查一下喔」）。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));
    // 上一輪的安撫話與答案都在他講第二句的時候才回來
    h.socket.emit({
      type: "ack",
      turn_id: "t1",
      text: "好，我幫您查一下喔",
      audio_url: "https://cdn.example/old-ack.m4a",
      duration_ms: 900,
    });
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      audio_url: "https://cdn.example/old-answer.m4a",
    });
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});
    // 這一輪的答案這時才回來
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t2",
      reply_digest: "d2",
      audio_url: "https://cdn.example/fresh.m4a",
    });
    // 讓補播的兩則依序播完，新那則才輪得到
    await act(async () => {
      h.player.finish();
    });
    await act(async () => {
      h.player.finish();
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/fresh.m4a"));
    const order = ["old-ack", "old-answer", "fresh"].map((name) =>
      h.player.played.indexOf(`https://cdn.example/${name}.m4a`),
    );
    expect(order[0]).toBeLessThan(order[1]);
    expect(order[1]).toBeLessThan(order[2]);
  });

  it("補播的舊答案播完、而新那一輪有字沒聲音時，畫面要回到待機", async () => {
    // 上一條的守門「輪次對不上就什麼都不做」有個縫：新那一輪**有字沒有聲音**
    //（TTS 掛掉或落地失敗）又剛好在收音期間抵達時，`onFrame` 那條「回到待機」因為
    // 畫面還歸長輩而沒有走到，播放佇列裡也就沒有東西接在舊答案後面——舊答案播完，
    // avatar 會停在「說話中」，長輩看著一張正在講話的臉、卻一個字都沒聽到。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));
    // 上一輪的答案（有聲音，兩段）
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      reply_digest: "dA",
      chunk_count: 2,
      audio_url: "https://cdn.example/A-c0.m4a",
    });
    // 再上一輪的答案有字沒聲音，但它把續拉佇列換成了自己那一輪
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t2",
      reply_digest: "dB",
      chunk_count: 2,
      audio_url: "",
    });
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});
    await waitFor(() => expect(h.view.result.current.avatar).toBe("speaking"));
    await act(async () => {
      h.player.finish();
    });
    expect(h.view.result.current.avatar).toBe("idle");
  });

  it("補播舊答案時，新一輪的安撫話不可以先把字幕搶走", async () => {
    // ⚠️ **2026-08-01 審查抓到的 Important**：`onFrame` 在收音狀態放開之後就會用新
    // 訊框的字覆蓋字幕，而舊答案的語音還要播八秒——長輩聽到「您的血壓藥早上吃一顆」，
    // 看到的卻是「好，我幫您查一下喔」。那正是本檔播放回呼自己寫下要避免的事。
    // ⚠️ 對**重聽**的長輩（本產品主客群）這不是美觀問題：字幕是他取得答案的另一半
    // 通道。這也是「補播不另加文案」這個決定唯一站得住的理由。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      text: "您的血壓藥早上吃一顆",
      audio_url: "https://cdn.example/old.m4a",
    });
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});
    expect(h.view.result.current.replyText).toBe("您的血壓藥早上吃一顆");

    // 新一輪的安撫話抵達——它自己的聲音還排在舊答案後面
    h.socket.emit({
      type: "ack",
      turn_id: "t2",
      text: "好，我幫您查一下喔",
      audio_url: "https://cdn.example/ack.m4a",
      duration_ms: 900,
    });
    await act(async () => {});
    expect(h.view.result.current.replyText).toBe("您的血壓藥早上吃一顆");

    // 等它自己的聲音真的播出來，字幕才換過去。
    await act(async () => {
      h.player.finish();
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/ack.m4a"));
    expect(h.view.result.current.replyText).toBe("好，我幫您查一下喔");
  });

  it("同一輪的答案在自己的安撫話播放中抵達時，字幕要立刻更新", async () => {
    // ⚠️ 上一條的守門**只能擋別一輪**：同一輪的 ack→reply 是後端的正常兩段式，
    // 那時字先出來是對的——對重聽的長輩，晚兩三秒才看到答案是實打實的損失。
    // 這一條擋的是「一律等自己的聲音播出來才顯示」那種過度收斂的寫法。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    await holdAndRelease(h);
    h.socket.emit({
      type: "ack",
      turn_id: "t1",
      text: "好，我幫您查一下喔",
      audio_url: "https://cdn.example/ack.m4a",
      duration_ms: 30_000,
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/ack.m4a"));
    // 答案回來時安撫話還在播（30 秒）
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      text: "您的血壓藥早上吃一顆",
      audio_url: "https://cdn.example/answer.m4a",
    });
    await act(async () => {});
    expect(h.view.result.current.replyText).toBe("您的血壓藥早上吃一顆");
  });

  it("連續插嘴時最多留兩則等補播，被擠掉的那一則要回收音檔", async () => {
    // ⚠️ 沒有上限的話，長輩連按好幾次之後會累積一串舊語音，最後補播的是幾分鐘前
    // 的問題——那正是 2026-07-31 選擇丟棄時的顧慮。上限取 2 ＝一輪最多兩則語音
    //（後端 ack→reply 兩段式），接得住一整輪的答案而不會變成一串。
    // ⚠️ 被擠掉的那一則從此不會再被 `replace()`，這裡不回收就沒有人回收了（一則
    // 語音數十到數百 KB，展示現場長輩插嘴是常態）。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));

    for (const [index, url] of ["blob:one", "blob:two", "blob:three"].entries()) {
      h.socket.emit({
        ...REPLY,
        type: "reply",
        turn_id: `t${index}`,
        reply_digest: `d${index}`,
        audio_url: url,
      });
    }
    await act(async () => {});
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});

    // 最舊的那一則被擠掉：不播，而且音檔要回收。
    expect(h.player.played).not.toContain("blob:one");
    expect(h.revokeReplyAudio).toHaveBeenCalledWith("blob:one");
    // 留下來的兩則照樣補播。
    expect(h.player.played).toContain("blob:two");
  });

  it("收音期間同一輪的四則全部收進同一個補播單位（Task 7，2026-08-01）", async () => {
    // ⚠️ 續段改由後端主動推之後，一輪會產生 ack＋reply＋chunk1＋chunk2 四則以上。
    // 若補播暫存仍以「則」計數、上限 2，這四則會在**單一輪之內**就把最早的兩則
    // （ack、第一句）擠掉——長輩插嘴後補播，只聽到「第二句。第三句。」，答案的
    // 開頭沒了。這裡驗證：不論一輪產生幾則，全部要歸進同一個補播單位，講完之後
    // 依抵達順序全數播出。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));
    // pressIn 這一下順手解鎖了播放器（見「iOS 音訊解鎖」那組），與本條驗的補播
    // 順序無關，清掉才能對 `played` 做精確的陣列比對。
    h.player.played.length = 0;

    h.socket.emit({
      type: "ack",
      turn_id: "t1",
      text: "好，我幫您查",
      audio_url: "blob:ack",
      duration_ms: 100,
    });
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      text: "第一句。",
      audio_url: "blob:a",
      duration_ms: 100,
      chunk_count: 3,
      reply_digest: "d",
    });
    h.socket.emit({
      type: "chunk",
      turn_id: "t1",
      index: 1,
      text: "第二句。",
      audio_url: "blob:b",
      duration_ms: 100,
      is_last: false,
    });
    h.socket.emit({
      type: "chunk",
      turn_id: "t1",
      index: 2,
      text: "第三句。",
      audio_url: "blob:c",
      duration_ms: 100,
      is_last: true,
    });
    await act(async () => {});

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});

    // 第一則（ack）補播時就地開播；其餘三則要靠佇列依序播完才輪得到。
    await act(async () => {
      h.player.finish();
    });
    await act(async () => {
      h.player.finish();
    });
    await act(async () => {
      h.player.finish();
    });

    expect(h.player.played).toEqual(["blob:ack", "blob:a", "blob:b", "blob:c"]);
    // 同一輪的四則沒有超過上限，不該有任何一則被擠掉回收。
    expect(h.revokeReplyAudio).not.toHaveBeenCalled();
  });

  it("補播佇列滿時擠掉最舊那一輪，不是最舊那一則（Task 7，2026-08-01）", async () => {
    // ⚠️ 上限改成「輪」之後，第三**輪**抵達才會擠掉最舊那一輪——即使每輪目前
    // 都只有一則，擠掉的單位仍然是輪（此處三輪各一則，行為上與擠掉「最舊一則」
    // 剛好等價，藉此確認以輪為單位時最單純的情形沒有壞掉）。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));
    // pressIn 這一下順手解鎖了播放器（見「iOS 音訊解鎖」那組），與本條驗的補播
    // 順序無關，清掉才能對 `played` 做精確的陣列比對。
    h.player.played.length = 0;

    for (const t of ["t1", "t2", "t3"]) {
      h.socket.emit({
        ...REPLY,
        type: "reply",
        turn_id: t,
        reply_digest: t,
        text: `${t} 的答案。`,
        audio_url: `blob:${t}`,
        duration_ms: 100,
        chunk_count: 0,
      });
    }
    await act(async () => {});

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});

    // 最舊那一輪（t1）被整輪擠掉：不播，音檔回收。
    expect(h.player.played).not.toContain("blob:t1");
    expect(h.revokeReplyAudio).toHaveBeenCalledWith("blob:t1");
    expect(h.revokeReplyAudio).not.toHaveBeenCalledWith("blob:t2");
    expect(h.revokeReplyAudio).not.toHaveBeenCalledWith("blob:t3");
    // 留下來的兩輪照樣依序補播。
    expect(h.player.played).toContain("blob:t2");

    await act(async () => {
      h.player.finish();
    });
    await waitFor(() => expect(h.player.played).toContain("blob:t3"));
    expect(h.player.played).toEqual(["blob:t2", "blob:t3"]);
  });

  it("開錄失敗時，排隊中那幾則也不可以趁機播出來", async () => {
    // ✅ 裁決 2026-08-01 改回補播之後，**開錄失敗是唯一還會丟棄的路徑**：長輩根本
    // 沒問出新問題，畫面上唯一該講的是「麥克風打不開，請再按一次試試看」，補播的話
    // 那句話會被舊回覆自己的字當場蓋掉——他就失去自救的唯一線索。
    // ⚠️ 這一條守的是「**還在佇列裡**就撞上開錄失敗」那半邊（`clear()`）：開錄失敗
    // 得夠快時，drain 還沒把排隊中那幾則交給播放回呼，它們一則都還沒進暫存。另外
    // 半邊（已經進了暫存）由下一條測試守——兩條缺一不可，實測拿掉 `clear()` 只有
    // 這一條變紅、拿掉清暫存只有下一條變紅。
    const h = setup({ startFails: true });
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({
      type: "ack",
      turn_id: "t1",
      text: "好，我幫您查一下喔",
      audio_url: "https://cdn.example/ack.m4a",
      duration_ms: 30_000,
    });
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1", audio_url: "https://cdn.example/queued.m4a" });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/ack.m4a"));
    expect(h.player.played).not.toContain("https://cdn.example/queued.m4a");

    act(() => h.view.result.current.pressIn());
    await act(async () => {
      h.recorder.finishStart();
    });
    await act(async () => {
      vi.advanceTimersByTime(40_000);
    });
    expect(h.view.result.current.replyText).toBe("麥克風打不開，請再按一次試試看。");
    expect(h.player.played).not.toContain("https://cdn.example/queued.m4a");

    // ⚠️ 開錄失敗之後收音狀態必須放開：沒放開的話，之後每一則回覆都會被當成
    // 「錄音中抵達」而丟掉——長輩從此聽不到任何回答，而他只是按了一次沒開成的
    // 麥克風。
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t2", audio_url: "https://cdn.example/after.m4a" });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/after.m4a"));
  });

  it("`recorder.stop()` 擲例外時，等補播的那幾則照樣要播出來", async () => {
    // ⚠️ 這條釘的是 `finally` 裡**兩行的順序**：先放開 `micActiveRef` 才補播。
    // 順序顛倒的話，補播推回佇列的那幾則會被播放回呼當成「收音中抵達」**再度收進
    // 暫存**，從此不再播出——長輩的那一題就此沒有答案。成功路徑上兩行等價（收音
    // 狀態在 `stop()` 回來時就放開了），只有 `stop()` 擲例外這條路徑走得到。
    const h = setup({ stopThrows: true });
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      audio_url: "https://cdn.example/pending.m4a",
    });
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});
    expect(h.player.played).toContain("https://cdn.example/pending.m4a");
  });

  it("開錄失敗那一輪收下來的回覆，不可以在下一輪成功的對話結尾冒出來", async () => {
    // ⚠️ 補播是「暫存起來、稍後再放」，所以每一條沒有走到補播的出口都必須把暫存
    // 清乾淨，否則它會安靜地躺著、等下一次有人講完話時才冒出來——長輩問了一句
    // 完全不相干的事，聽到的卻是幾分鐘前那一輪的答案。
    // ⚠️ 而且開錄失敗時那幾則的音檔**已經被回收**（見上一條），留著它們補播等於
    // 讓播放器拿到一個失效的 blob URL：畫面上有字、完全沒有聲音，查起來很久。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({
      type: "ack",
      turn_id: "t1",
      text: "好，我幫您查一下喔",
      audio_url: "https://cdn.example/ack.m4a",
      duration_ms: 30_000,
    });
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1", audio_url: "https://cdn.example/stale.m4a" });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/ack.m4a"));

    // 這一次插嘴，麥克風就是打不開。
    // ⚠️ 刻意先把微任務跑完再讓開錄失敗：那一步會讓 drain 把排隊中的那一則真的
    // 交給播放回呼、收進暫存。少了它，那一則還躺在佇列裡，這條測試守到的就變成
    // 上一條已經守著的 `clear()`（實測過：不先跑微任務的話，拿掉清暫存仍然全綠）。
    act(() => h.view.result.current.pressIn());
    await act(async () => {});
    h.recorder.failNextStart = true;
    await act(async () => {
      h.recorder.finishStart();
    });
    expect(h.view.result.current.replyText).toBe("麥克風打不開，請再按一次試試看。");

    // 下一次按下去麥克風正常，走完整整一輪
    await holdAndRelease(h);
    await act(async () => {});
    expect(h.recorder.stopped).toBe(1);
    expect(h.player.played).not.toContain("https://cdn.example/stale.m4a");
  });

  it("打斷一則長回覆之後，下一句的語音要立刻播，不必等舊那則的保險逾時", async () => {
    // ⚠️ **審查抓到的 Critical 3**：`pause()` 之後 `ended` 永遠不會來，`playAndWait`
    // 只能等滿「時長＋3 秒」的保險；那期間 `createPlaybackQueue` 的 `running` 是
    // true，新回覆只能排隊。審查實跑：一則 30 秒的回覆播到第 1 秒被打斷、後端 3 秒
    // 後回覆，新答案的**字**出現了但**語音再過 29 秒才播**，這 29 秒內 avatar 停在
    // 「在想」、麥克風鍵按不動。75 秒保險也救不了——訊框有到，它剛被重新起算。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      audio_url: "https://cdn.example/long.m4a",
      duration_ms: 30_000,
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/long.m4a"));

    // 長輩插嘴問新問題
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    // 後端三秒後回覆（遠早於舊那則的 30000+3000 保險）
    await act(async () => {
      vi.advanceTimersByTime(3000);
    });
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t2",
      reply_digest: "d2",
      audio_url: "https://cdn.example/fresh.m4a",
      duration_ms: 1200,
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/fresh.m4a"));
    expect(h.view.result.current.avatar).toBe("speaking");
  });

  it("開錄失敗時把等補播的那幾則一起丟掉並回收，正在播的那一則不可回收", async () => {
    // ⚠️ Task 4 留下的缺口（Important 5 的剩下一半）：`queue.clear()` 只把項目
    // 從佇列丟掉，那些 blob URL 一個都不會被回收——瀏覽器不會替你清，它不知道
    // 你不再需要它了。展示現場長輩插嘴是常態，一則語音數十到數百 KB。
    // ✅ **裁決 2026-08-01 之後，開錄失敗是唯一還會丟棄的路徑**（其餘一律補播）：
    // 長輩根本沒問出新問題，畫面上唯一該講的是「麥克風打不開，請再按一次試試看」，
    // 補播的話那句話會被舊回覆自己的字當場蓋掉，他就失去自救的唯一線索。
    const h = setup({ startFails: true });
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1" });
    await waitFor(() => expect(h.player.played.length).toBe(1));
    act(() => h.view.result.current.pressIn());
    await act(async () => {
      h.recorder.finishStart();
    });
    // 傳的是「要留著的那一則」＝正在播的（src 還掛在播放器上）；其餘一律回收。
    await waitFor(() =>
      expect(h.revokeQueuedReplyAudio).toHaveBeenCalledWith("https://cdn.example/a.m4a"),
    );
  });
});

describe("續段直送（2026-08-01）", () => {
  // ⚠️ 後端已改為主動從同一條連線推續段（新的 `type: "chunk"` 訊框），前端不再
  // 靠 REST 去拉——`getTurnChunk`／`prefetchNext`／`ChunkQueue` 那整套已經隨這次
  // 任務移除（見 `useTalk.ts::advanceQueue` 該處說明），不再是「刻意不動」的舊
  // 路徑，而是不存在的路徑。
  //
  // ⚠️ **已知的測試覆蓋缺口**：移除 REST 續拉時一併拿掉的「輪次比對」
  //（`459051f` 引入的 `queue.turnId !== playingTurnIdRef.current`）曾經有一條
  // 專屬測試守著「補播舊答案時，續段接的是舊那一輪、不會接到新那一輪的中段」。
  // 那個機制存在的理由（REST 續拉的共用可變狀態 `chunkQueueRef` 會被補播覆寫）
  // 已隨機制一起消失，所以那條測試也跟著刪除——**但它原本守住的「長輩不會聽到
  // 錯亂的答案」這件事，現在沒有等價的測試覆蓋**，只由「訊框通常依抵達順序送達」
  // 這個機率性質支撐。播放順序改為完全依訊框抵達順序後，理論上仍存在「A 的續段
  // 合成得比 B 的整輪還慢，導致 `[A0, B0, A1]`」這種錯亂序列（估算與理由見
  // `useTalk.ts::advanceQueue` 上方註解），只是目前沒有被寫成測試、也未在瀏覽器
  // 上實測過。
  it("收到 chunk 訊框就進播放佇列，依 index 順序播", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      audio_url: "https://cdn.example/a.m4a",
      chunk_count: 1,
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/a.m4a"));
    h.socket.emit({
      type: "chunk",
      turn_id: "t1",
      index: 1,
      text: "第二句。",
      audio_url: "https://cdn.example/b.m4a",
      duration_ms: 100,
      is_last: false,
    });
    h.socket.emit({
      type: "chunk",
      turn_id: "t1",
      index: 2,
      text: "第三句。",
      audio_url: "https://cdn.example/c.m4a",
      duration_ms: 100,
      is_last: true,
    });
    // 第一段播完 → 接第二段
    await act(async () => {
      h.player.finish();
    });
    // 第二段播完 → 接第三段
    await act(async () => {
      h.player.finish();
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/c.m4a"));
    expect(h.player.played).toEqual([
      "https://cdn.example/a.m4a",
      "https://cdn.example/b.m4a",
      "https://cdn.example/c.m4a",
    ]);
  });

  it("沒有更多續段時，這一則播完就回到待機", async () => {
    // ⚠️ 這條釘住 `advanceQueue` 拿掉 REST 拉取邏輯後唯一剩下的責任——「播放
    // 佇列空了就回到待機」，不靠續段的終止訊框附帶測到（下一條的重點是「終止
    // 訊框不進佇列」，兩者刻意分開）。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      audio_url: "https://cdn.example/a.m4a",
      chunk_count: 1,
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/a.m4a"));
    await act(async () => {
      h.player.finish();
    });
    expect(h.view.result.current.avatar).toBe("idle");
  });

  it("空音檔的終止訊框不進播放佇列", async () => {
    // ⚠️ 續段合成失敗、或本來就切不出第二段時，後端會補送一則 `index=0`、
    // `text=""`、音檔位元組長度為 0、`is_last=true` 的終止訊框，只用來標示
    // 「這輪講完了」，不可以進播放佇列——播出一段 0 位元組的音檔沒有意義。
    // ⚠️ `chunk_count: 1` 起手：不代表還在避開什麼 REST 路徑（那條路徑已經不
    // 存在），純粹是沿用 `REPLY` 這個共用 fixture 的預設值。
    // ⚠️ 光是「emit 之後 played 只有一個元素」不夠——終止訊框若被誤推進佇列，
    // 它會排在第一段**後面**，drain 要等第一段播完才輪得到它，emit 完當下
    // 播放佇列還沒走到那裡，斷言測不出來（實測過這個假陰性）。這裡讓第一段
    // 播完、逼佇列真的往下走一步，才驗得到「終止訊框沒有被排進去」。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      audio_url: "https://cdn.example/a.m4a",
      chunk_count: 1,
    });
    await waitFor(() => expect(h.player.played).toContain("https://cdn.example/a.m4a"));
    h.socket.emit({
      type: "chunk",
      turn_id: "t1",
      index: 0,
      text: "",
      audio_url: "",
      duration_ms: 0,
      is_last: true,
    });
    // 第一段播完：若終止訊框被誤推進佇列，drain 這時就會去接它。
    await act(async () => {
      h.player.finish();
    });
    expect(h.player.played).toEqual(["https://cdn.example/a.m4a"]);
    // 畫面要回到待機——沒有下一段可播，不可以停在「說話中」。
    await waitFor(() => expect(h.view.result.current.avatar).toBe("idle"));
  });
});

describe("下行訊框", () => {
  it("排隊時告訴長輩排第幾位，而不是沉默", async () => {
    // ⚠️ 靜默排隊與當機對長輩來說長得一模一樣，他只會再講一次——而那會讓已經
    // 滿載的 GPU 雪上加霜。
    // ⚠️ `position` 是排隊名次（1-based），不是「前面還有幾位」（見 strings.ts
    // 對這個鍵的說明與 06_API設計規範 §5）。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({ type: "queued", turn_id: "t1", position: 2 });
    await waitFor(() =>
      expect(h.view.result.current.replyText).toBe("金孫正在跟別人說話，您排第 2 位…"),
    );
  });

  it("錯誤訊框直接顯示後端寫好的那句話，並讓長輩可以再講一次", async () => {
    // ⚠️ **修正 brief 的一條假測試**：原始版本從待機狀態直接餵一則 error 訊框，
    // 然後斷言 avatar 是 "idle"——而它本來就是 "idle"。實測變異：把 error 分支
    // 的 `setAvatarBoth("idle")` 整行刪掉，那一版仍然全綠，而真實情境（長輩講完
    // → 在想 → 後端回錯誤）下畫面會永遠停在「金孫想一下…」、麥克風鍵永遠停用。
    // 這裡先走完一次送出，讓斷言真的有東西可以驗。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    await holdAndRelease(h);
    expect(h.view.result.current.avatar).toBe("thinking");
    h.socket.emit({ type: "error", turn_id: "t1", text: "金孫有點忙，等一下再說好嗎" });
    await waitFor(() => expect(h.view.result.current.replyText).toBe("金孫有點忙，等一下再說好嗎"));
    expect(h.view.result.current.avatar).toBe("idle");
  });

  it("回覆只有字沒有聲音時也要回到待機，不可停在「金孫想一下…」", async () => {
    // ⚠️ TTS 服務掛掉（開場的運營狀態頁自己就有這一種降級：「回答只會顯示文字」）
    // 或音檔落地失敗時，reply 訊框的 audio_url 是空的。只看 audio_url 決定要不要
    // 播、卻不管沒有音檔的情形，畫面會永遠停在「金孫想一下…」而麥克風鍵一直是
    // 停用的——長輩從此按不動，而他做錯的事只是問了一句話。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    await holdAndRelease(h);
    expect(h.view.result.current.avatar).toBe("thinking");
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1", audio_url: "" });
    await waitFor(() => expect(h.view.result.current.avatar).toBe("idle"));
    expect(h.view.result.current.replyText).toBe("今天天氣很好");
  });
});

describe("等不到回話的保險", () => {
  it("送出後完全沒有回應時，長輩仍然可以再講一次", async () => {
    // ⚠️ 連線斷在半路（隧道抖一下）、或後端那一輪掉了的時候，沒有任何訊框會
    // 回來。沒有這道保險，畫面永遠停在「金孫想一下…」、麥克風鍵永遠停用——
    // 長輩按了沒反應，而畫面上沒有任何說明。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    await holdAndRelease(h);
    expect(h.view.result.current.avatar).toBe("thinking");
    await act(async () => {
      vi.advanceTimersByTime(80_000);
    });
    expect(h.view.result.current.avatar).toBe("idle");
    expect(h.view.result.current.replyText).toBe("金孫這次沒有回話，再說一次好嗎？");
  });

  it("排隊訊框會讓保險重新起算，排隊中的長輩不可被自己的保險打斷", async () => {
    // 後端排隊逾時 30 秒＋單輪預算 30 秒，排到的人本來就會等很久；保險若不隨
    // 下行訊框重新起算，會在他還好好排著隊的時候跳出「金孫這次沒有回話」。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    await holdAndRelease(h);
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    h.socket.emit({ type: "queued", turn_id: "t1", position: 1 });
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(h.view.result.current.avatar).toBe("thinking");
  });
});

describe("降級與失敗", () => {
  it("長連線沒開時退回 POST", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    // 刻意不呼叫 socket.open()
    await holdAndRelease(h);
    await waitFor(() => expect(h.postTurn).toHaveBeenCalledTimes(1));
    expect(h.view.result.current.replyText).toBe("今天天氣很好");
    // 送出的必須是錄到的那段音檔與這支 token——沒有這條斷言，`postTurn()` 少傳
    // 一個參數也照樣全綠，而長輩的錄音一個位元組都不會離開瀏覽器。
    const [audio, sentToken, sentPlace] = h.postTurn.mock.calls[0];
    expectRecordedAudio(audio);
    expect(sentToken).toBe("tok");
    // null＝這輪沒有位置（網頁端拿不到地名，見 elder/location.ts），不是空字串。
    expect(sentPlace).toBeNull();
  });

  it("錄到的是空音檔時不送出，並告訴長輩再說一次", async () => {
    // 手指一碰就放（或系統把軌道搶走），`MediaRecorder` 一個位元組都沒收到。
    // 照送的話後端只會回一句聽不懂，白白吃掉一輪 GPU 與長輩的耐心。
    const h = setup({ emptyRecording: true });
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    await holdAndRelease(h);
    await waitFor(() => expect(h.view.result.current.avatar).toBe("idle"));
    expect(h.postTurn).not.toHaveBeenCalled();
    expect(h.socket.sent.some((item) => item instanceof ArrayBuffer)).toBe(false);
    expect(h.view.result.current.replyText).toBe("金孫沒聽清楚，再說一次好嗎？");
  });

  it("金孫還在想的時候又按下去，不會再開一次錄音", async () => {
    // 畫面上麥克風鍵這時是停用的，但停用只是瀏覽器層的第一道防線——`useTalk`
    // 自己也要守住。開了第二次錄音的話，第一輪的回覆回來時長輩正在講第二句，
    // 金孫的聲音會被錄進去。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    await holdAndRelease(h);
    expect(h.view.result.current.avatar).toBe("thinking");
    await act(async () => {
      h.view.result.current.pressIn();
    });
    expect(h.recorder.started).toBe(1);
  });

  it("播放中插嘴卻打不開麥克風時，說的是「麥克風打不開」，畫面也要回到待機", async () => {
    // 進畫面探測得到麥克風，真的按下去那一刻卻開不起來（裝置忙、系統把軌道
    // 收走）。
    // ⚠️ 這時說「金孫沒聽清楚，再說一次好嗎？」是錯的——錄音根本沒開始，那句
    // 話會讓長輩以為是自己講得不夠大聲，於是一次比一次更用力喊。
    // ⚠️ 刻意從**播放中**插嘴（而不是從待機按下去）：從待機按的話 avatar 本來
    // 就是 idle，「失敗時回到待機」那一行刪掉也照樣全綠——實測過這個變異。從
    // 播放中插嘴才驗得到它，而畫面停在「說話中」的話長輩會一直等一個不會來的
    // 聲音。
    const h = setup({ startFails: true });
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1" });
    await waitFor(() => expect(h.view.result.current.avatar).toBe("speaking"));
    act(() => h.view.result.current.pressIn());
    await act(async () => {
      h.recorder.finishStart();
    });
    expect(h.view.result.current.replyText).toBe("麥克風打不開，請再按一次試試看。");
    expect(h.view.result.current.avatar).toBe("idle");
  });

  it("開錄失敗之後手勢要復位，下一次按下去是真的重新開始錄音", async () => {
    // ⚠️ 審查發現這行（`gestureRef.current.reset()`）刪掉全套仍綠。後果：麥克風
    // 打不開之後，長輩下一次按下去會被手勢狀態機判成「短按切換的第二下」，
    // `stopAndSend` 因 `started === false` 直接返回——**那一按完全沒有反應**，
    // 要按第三下才會真的開始錄音。
    const h = setup({ startFails: true });
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    act(() => h.view.result.current.pressIn());
    await act(async () => {
      h.recorder.finishStart();
    });
    expect(h.recorder.started).toBe(1);
    // 第二次按下去必須是「重新開始錄音」，不是被當成第二下而什麼都沒發生。
    act(() => h.view.result.current.pressIn());
    expect(h.recorder.started).toBe(2);
  });

  it("麥克風被拒時顯示白話說明，且不再開錄", async () => {
    const h = setup({ granted: false });
    await waitFor(() => expect(h.view.result.current.micReady).toBe(false));
    expect(h.view.result.current.replyText).toContain("麥克風");
    act(() => h.view.result.current.pressIn());
    expect(h.recorder.started).toBe(0);
  });

  it.each([
    ["denied", "需要麥克風權限才能跟金孫說話，請到設定開啟。"],
    ["not-found", "這台裝置沒有麥克風，請換一台有麥克風的手機或平板。"],
    ["in-use", "麥克風正被別的畫面用著，請把其他在錄音或講電話的畫面關掉再試一次。"],
    ["insecure-origin", "這個網址不能錄音，請改用家人給您、開頭是 https 的網址。"],
    ["unsupported", "這個瀏覽器不能錄音，請換 Chrome、Safari 或 Firefox。"],
  ])("麥克風問題 %s 說的是長輩能照做的話", async (probe, expected) => {
    // 「請到設定開啟」對沒有麥克風的桌機、對用區網 IP 連進來的組員都是錯的
    // 指示——他們會去找一個不存在的開關。與相機的六種錯誤同一套原則。
    const h = setup({ granted: false, micProbe: probe as MicrophoneProbeResult });
    await waitFor(() => expect(h.view.result.current.replyText).toBe(expected));
    expect(h.view.result.current.micReady).toBe(false);
  });

  it("綁定失效時通知呼叫端，讓它把人導回配對", async () => {
    const h = setup();
    h.postTurn.mockRejectedValue(new ApiError(403, "consent_revoked"));
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    await holdAndRelease(h);
    await waitFor(() => expect(h.onBindingLost).toHaveBeenCalledOnce());
    expect(h.view.result.current.replyText).toContain("綁定");
  });

  it.each([
    [503, "too_many_requests", "金孫還在忙前面那幾句，等一下下再跟您說好嗎？"],
    [429, "too_many_requests", "金孫還在忙前面那幾句，等一下下再跟您說好嗎？"],
    [413, "audio_too_large", "音檔太大，請縮短錄音再試一次"],
  ])("POST 降級路徑吃到 %s 時，長輩看到的是後端那句人話", async (status, code, message) => {
    // ⚠️ **全分支審查抓到的 Important 1**：這幾句全部被收斂成「金孫沒聽清楚，再說
    // 一次好嗎？」。失效情境：GPU 滿載、長連線又剛好連不上 → 長輩講一句 → 503 →
    // 他看到「沒聽清楚」→ **更大聲再講一次** → 又一輪打進已經滿載的閘門。閘門存在
    // 的理由就是避免這件事，而降級路徑親手製造它。
    // ⚠️ 斷言寫死字面值：這是後端 `channels/app/ws.py::_BUSY_REPLY` 與
    // `web/envelope.py` 的既有文案，測試要在它被前端吃掉時變紅。
    const h = setup();
    h.postTurn.mockRejectedValue(new ApiError(status, code, message));
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    await holdAndRelease(h);
    await waitFor(() => expect(h.view.result.current.replyText).toBe(message));
    // 講完還是要能再按（他等一下確實可以再講一次）。
    expect(h.view.result.current.avatar).toBe("idle");
  });

  it("後端回的不是人話（隧道抖動的 HTTP 502）時，仍講長輩看得懂的那句", async () => {
    // ⚠️ `shared/client.ts` 在回應不是合法信封時自造 `http_<status>` 的英文訊息
    //（字面值就是「HTTP 502」）。直接顯示的話長輩會在畫面正中央看到一串英數字。
    const h = setup();
    h.postTurn.mockRejectedValue(new ApiError(502, "http_502", "HTTP 502"));
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    await holdAndRelease(h);
    await waitFor(() =>
      expect(h.view.result.current.replyText).toBe("金孫沒聽清楚，再說一次好嗎？"),
    );
  });

  it("token 被撤銷（401）時通知呼叫端，不可以只說「金孫沒聽清楚」", async () => {
    // ⚠️ **全分支審查抓到的 Critical 1**：家屬按下「重新產生長輩綁定碼」時，後端
    // `accounts/service.py::revoke_elder_device` 是**先**撤 token **再**拆綁定，
    // 於是 `turns.py::current_elder` 在認證那一步就回 401，永遠走不到後面那個 403。
    // 只接 403 的話，長輩每按一次麥克風都只看到「金孫沒聽清楚，再說一次好嗎？」，
    // 他就一次比一次更大聲地再講一遍；重新整理也沒用（token 在 localStorage、
    // 初始路由仍是對講機），而家屬手上那組新碼永遠沒有畫面可以輸入。
    const h = setup();
    h.postTurn.mockRejectedValue(new ApiError(401, "invalid_token"));
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    await holdAndRelease(h);
    await waitFor(() => expect(h.onTokenRevoked).toHaveBeenCalledOnce());
    // 403 是另一回事（同意被撤回、token 還有效），不可以順手一起通知。
    expect(h.onBindingLost).not.toHaveBeenCalled();
    // 麥克風鍵要能再按（畫面接下來會被呼叫端換成配對畫面，但這一層不可以卡在「在想」）。
    expect(h.view.result.current.avatar).toBe("idle");
  });
});

describe("這一欄被切到背景", () => {
  it("切走時停止錄音、關掉長連線、丟掉播放器，麥克風不可留著亮", async () => {
    // ⚠️ 同一類坑的第四次（Task 4 麥克風、Task 5／7 相機）：雙欄舞台在窄螢幕是
    // 頁籤擇一顯示，非活動欄只是被 CSS `hidden` 蓋住——元件仍掛著，`MediaStream`
    // 軌道與 `display:none` 無關，會一直開到分頁關閉。長輩講到一半切去看家屬端，
    // 麥克風指示燈就一直亮著。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));

    h.view.rerender({ visible: false });

    await waitFor(() => expect(h.recorder.stopped).toBe(1));
    expect(h.socket.socket?.closed).toBe(1);
    expect(h.player.disposed).toBe(1);
    expect(h.revokeQueuedReplyAudio).toHaveBeenCalled();
    expect(h.view.result.current.avatar).toBe("idle");
  });

  it("切走時等補播的那幾則要一起丟掉，不可以在切回來之後才冒出來", async () => {
    // ⚠️ 切走時 `revokeQueuedReplyAudio()` 會**不帶例外地全掃回收**，等補播的那幾則
    // 音檔在那一刻就死了。暫存若沒跟著清空，切回來之後長輩講完的第一句話，結尾會
    // 接上一段上一輪的舊回覆——而且是**有字沒有聲音**的那種（blob URL 已失效），
    // 看起來就像對講機壞了。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1", audio_url: "https://cdn.example/stale.m4a" });
    await act(async () => {});
    expect(h.player.played).not.toContain("https://cdn.example/stale.m4a");

    h.view.rerender({ visible: false });
    h.view.rerender({ visible: true });
    h.socket.open();
    await holdAndRelease(h);
    await act(async () => {});
    expect(h.player.played).not.toContain("https://cdn.example/stale.m4a");
  });

  it("切走再切回來之後，新的播放器要在使用者手勢內重新解鎖", async () => {
    // ⚠️ **審查抓到的 Critical 1**：`audioUnlock` 的旗標原本是**每個頁面一次**，
    // 而播放器是**每次 effect 重跑一顆新的**（`createWebPlayer()` 每次都 `new Audio()`，
    // 而長連線 effect 的相依含 `visible`）。`playback.ts` 自己寫著「iOS 的解鎖綁在
    // 單一 HTMLMediaElement 上，換一顆播放器等於沒解鎖」——所以 iPhone 上切一次
    // 頁籤（或登出後重新配對，`TalkScreen` 重新掛載）之後，新播放器從未在使用者
    // 手勢內被 play() 過，`playAndWait` 的 play() 被 iOS 擋下、rejection 被
    // `playback.ts` 靜靜吞掉——長輩只看得到字、聽不到任何聲音，本次頁面載入內
    // 永久如此。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    expect(h.player.played).toContain("/demo/silent.wav");

    h.player.played.length = 0;
    h.view.rerender({ visible: false });
    h.view.rerender({ visible: true });
    expect(h.player.created).toBe(2);

    act(() => h.view.result.current.pressIn());
    expect(h.player.played).toContain("/demo/silent.wav");
  });

  it("切回來時重新連線，而且那句話是走**新**連線送出去的", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    const firstSocket = h.socket.socket;
    h.view.rerender({ visible: false });
    h.view.rerender({ visible: true });
    expect(h.socket.socket).not.toBe(firstSocket);
    h.socket.open();
    await holdAndRelease(h);
    expect(h.recorder.stopped).toBe(1);
    expect(h.socket.sent.some((item) => item instanceof ArrayBuffer)).toBe(true);
    // ⚠️ 舊那條連線已經 `close()` 過了，往它送出去的東西不會抵達後端——長輩會覺得
    // 金孫從此不理他。
    //
    // ⚠️ **誠實說明這條斷言的份量**：目前的實作在結構上踩不到它（effect 的 cleanup
    // 會把 `socketRef.current` 清成 `null`、下一輪 effect 一定重新指派），實測找不到
    // 任何**單一**產品變異能讓它獨自變紅。留著是因為它守的是一個很可能被改動的形狀：
    // P4 若為了省下切頁籤時的重連而改成「重用上一條連線」，這一行會立刻變紅。
    // 它同時也是 `sent` 改成每條連線各自持有的理由——在全域共用一份 `sent` 的舊寫法
    // 下，這句話**寫不出來**（送到哪一條連線都記在同一份陣列裡，它恆為 true）。
    expect(firstSocket?.sent.some((item) => item instanceof ArrayBuffer)).toBe(false);
  });

  it("舊連線晚到的斷線通知，不可以把新連線的狀態洗掉", async () => {
    // ⚠️ 審查發現的舊回呼競態：快速切走再切回來時，舊連線的 `onclose` 可能在新連線
    // 的 `onopen` **之後**才抵達，把 `socketOpenRef` 洗回 false。後果有限（那一輪
    // 改走 POST 降級，仍講得了話，只是沒有安撫話、延遲較長），但那是真的沒有防護
    // 的競態。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    const firstSocket = h.socket.socket;
    h.view.rerender({ visible: false });
    h.view.rerender({ visible: true });
    h.socket.open();
    // 舊連線的斷線通知這時才姍姍來遲
    act(() => {
      firstSocket?.onclose?.({} as CloseEvent);
    });
    await holdAndRelease(h);
    expect(h.postTurn).not.toHaveBeenCalled();
    expect(h.socket.sent.some((item) => item instanceof ArrayBuffer)).toBe(true);
  });

  it("元件卸載時同樣停止錄音、關掉長連線", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));

    h.view.unmount();

    await waitFor(() => expect(h.recorder.stopped).toBe(1));
    expect(h.socket.socket?.closed).toBe(1);
    expect(h.player.disposed).toBe(1);
  });
});

describe("暖定位權限（F-17 第二段，2026-08-01）", () => {
  it("進畫面就呼叫 currentPlace 暖權限，不必等長輩按下麥克風", async () => {
    // ⚠️ 這條守的正是本輪的重點：權限請求要在「進畫面」這個安全時機完成，
    // 不能等到按下麥克風才問（那正是本輪要避免重演的坑）。
    const h = setup();
    await waitFor(() => expect(h.currentPlace).toHaveBeenCalledTimes(1));
    expect(h.recorder.started).toBe(0);
  });

  it("即使麥克風被拒，暖定位權限的呼叫依然會發生——兩條 mount effect 互不依賴", async () => {
    // 這條守住「獨立成另一條 effect」這個設計決策：暖定位權限不可以被誰改成
    // 「等麥克風准了才問」，那樣會讓拒絕麥克風的長輩連定位都問不到。
    const h = setup({ granted: false });
    await waitFor(() => expect(h.view.result.current.micReady).toBe(false));
    expect(h.currentPlace).toHaveBeenCalledTimes(1);
  });

  it("開錄時仍會再呼叫一次 currentPlace，取得送出當下的座標——暖權限不取代這一行", async () => {
    // `startRecording()` 既有那行呼叫本輪刻意保留不動：暖權限只負責讓瀏覽器
    // 提早問完權限，實際要送出的座標仍在開錄當下重新取一次。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    await waitFor(() => expect(h.currentPlace).toHaveBeenCalledTimes(1));
    h.socket.open();
    await holdAndRelease(h);
    expect(h.currentPlace).toHaveBeenCalledTimes(2);
  });

  it("暖定位權限只在進畫面時發生一次，不會因為切換分頁可見度而重複呼叫", async () => {
    // `deps` 在本元件生命週期內只算一次（見 useTalk.ts 檔頭），這條 effect
    // 的相依陣列只有 `[deps]`，故不該隨 `visible` 切換而重跑。
    const h = setup();
    await waitFor(() => expect(h.currentPlace).toHaveBeenCalledTimes(1));
    h.view.rerender({ visible: false });
    h.view.rerender({ visible: true });
    expect(h.currentPlace).toHaveBeenCalledTimes(1);
  });
});
