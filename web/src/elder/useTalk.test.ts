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
function makeRecorder(options: { granted?: boolean; emptyRecording?: boolean } = {}) {
  const granted = options.granted ?? true;
  let resolveStart: ((value: boolean) => void) | null = null;
  const api = {
    started: 0,
    stopped: 0,
    /** 讓最近一次還沒完成的 `start()` 收工。 */
    finishStart() {
      resolveStart?.(granted);
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

/** 可以由測試決定何時「連上」、並直接餵下行訊框的假 WebSocket。 */
function makeSocket() {
  const api = {
    sent: [] as (string | ArrayBuffer)[],
    socket: null as FakeWebSocket | null,
    factory(url: string) {
      api.socket = new FakeWebSocket(url, api.sent);
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
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  constructor(
    public url: string,
    private sink: (string | ArrayBuffer)[],
  ) {}
  send(payload: string | ArrayBuffer) {
    this.sink.push(payload);
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
  }> = {},
) {
  const granted = overrides.granted ?? true;
  const harness = {
    recorder: makeRecorder({
      granted: granted && !overrides.startFails,
      emptyRecording: overrides.emptyRecording,
    }),
    player: makePlayer(),
    socket: makeSocket(),
    postTurn: vi.fn().mockResolvedValue(REPLY),
    getTurnChunk: vi
      .fn()
      .mockResolvedValue({ audio_url: "https://cdn.example/c1.m4a", duration_ms: 900, text: "" }),
    currentPlace: vi.fn().mockResolvedValue(null),
    revokeQueuedReplyAudio: vi.fn(),
    onBindingLost: vi.fn(),
  };
  const view = renderHook(
    (props: { visible: boolean }) =>
      useTalk({
        token: "tok",
        visible: props.visible,
        onBindingLost: harness.onBindingLost,
        deps: {
          createRecorder: () => harness.recorder.create(),
          createPlayer: () => harness.player.create(),
          createSocket: harness.socket.factory,
          postTurn: harness.postTurn,
          getTurnChunk: harness.getTurnChunk,
          currentPlace: harness.currentPlace,
          revokeQueuedReplyAudio: harness.revokeQueuedReplyAudio,
          probeMicrophone: vi
            .fn()
            .mockResolvedValue(overrides.micProbe ?? (granted ? "granted" : "denied")),
        },
      }),
    { initialProps: { visible: true } },
  );
  return { ...harness, view };
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

  it("第一次按下麥克風時解鎖音訊，之後 WebSocket 送下來的回覆才播得動", async () => {
    // ⚠️ iOS Safari 不允許在沒有使用者手勢的情況下播放音訊，而金孫的回覆是在
    // 訊框抵達時才播——那已經脫離手勢鏈。不做的話症狀是「iPhone 上只看得到字、
    // 聽不到聲音，桌機一切正常」。
    // ⚠️ 這個時機（與開錄同一個手勢）是有風險的取捨，見任務報告的人工驗收清單。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    act(() => h.view.result.current.pressIn());
    // 寫死字面值而非讀常數：這是與後端靜態檔位置（`web/public/silent.wav` →
    // `/demo/silent.wav`）之間的契約，兩邊各自改到才算改對。
    expect(h.player.played[0]).toBe("/demo/silent.wav");
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

  it("開錄之前先清掉還沒播的、並暫停正在播的", async () => {
    // ⚠️ 不清的話金孫自己的聲音會被錄進去。
    //
    // ⚠️ **審查抓到的第十八個假測試**：brief 這條原本只 emit 一則訊框，而它立刻
    // 被播掉——`clear()` 被呼叫時佇列本來就是空的，這條測試在結構上不可能觀察到
    // 「清掉」那一半。實測：把 `playQueueRef.current?.clear()` 整行刪掉，30 條全綠。
    // 要有鑑別力就得讓佇列裡**真的有東西在排隊**：後端的 ack→reply 兩段式正好會
    // 連續送兩則，第一則播著、第二則在等。
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
    await act(async () => {
      h.view.result.current.pressOut();
    });
    // 排隊中被丟掉的那一則同樣是「被跳過的回覆」，要跟收音期間才抵達的那些一視同仁
    //（✅ 裁決：抵達時機是實作細節）——不可以靜默丟棄。
    expect(h.view.result.current.replyText).toBe("上一個問題就先跳過了，金孫想一下…");
    // ⚠️ 走完整輪都不可以聽到排隊中的那一則——它在長輩按下去的那一刻就該被丟掉。
    await act(async () => {
      vi.advanceTimersByTime(40_000);
    });
    expect(h.player.played).not.toContain("https://cdn.example/second.m4a");
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

  it("收音期間抵達的回覆一律丟棄，收音結束也不補播——但要告訴長輩上一個問題跳過了", async () => {
    // ✅ **專案裁決 2026-07-31**：同一類東西（一個已被跳過的回合、還沒被聽到的
    // 回覆）不該因為抵達時機不同而有不同待遇——按下麥克風的語意就是「我現在要
    // 講話，你先別說」，抵達時機是實作細節。而對長輩更糟的是「突然冒出來的
    // 聲音」：他問了 A、等不及改問 B，十秒後金孫開始回答 A——他不會記得自己問過
    // A，只會覺得金孫在自言自語。這與「打斷就是打斷、不要留半條尾巴在後面追上
    // 來」（Critical 3）是同一個方向。
    // ⚠️ 但**不可以靜默丟棄**：長輩要知道那一句不會有答案了、不必再等。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    await waitFor(() => expect(h.view.result.current.avatar).toBe("listening"));

    const revokedBefore = h.revokeQueuedReplyAudio.mock.calls.length;
    h.socket.emit({
      ...REPLY,
      type: "reply",
      turn_id: "t1",
      text: "附近有 205 跟 622",
      audio_url: "https://cdn.example/answer.m4a",
    });
    await act(async () => {});
    expect(h.player.played).not.toContain("https://cdn.example/answer.m4a");
    // 丟掉的那一則若是 WS 直送落地的 blob URL，沒有人會再去 replace() 它——這裡
    // 不回收就沒有人回收了。
    expect(h.revokeQueuedReplyAudio.mock.calls.length).toBeGreaterThan(revokedBefore);

    await act(async () => {
      vi.advanceTimersByTime(600);
    });
    await act(async () => {
      h.view.result.current.pressOut();
    });
    await act(async () => {});
    // 收音結束也不補播。
    expect(h.player.played).not.toContain("https://cdn.example/answer.m4a");
    // 但要講出來，不可以靜默丟棄。
    expect(h.view.result.current.replyText).toBe("上一個問題就先跳過了，金孫想一下…");

    // 下一輪沒有東西被跳過，就不可以再講一次——那句話會變成謎語。
    h.socket.emit({ type: "error", turn_id: "t1", text: "金孫有點忙，等一下再說好嗎" });
    await holdAndRelease(h);
    expect(h.view.result.current.replyText).toBe("金孫想一下…");
  });

  it("開錄失敗時，排隊中那幾則也不可以趁機播出來", async () => {
    // `clear()` 在多數路徑上與「收音中抵達就丟掉」那道守門重疊（兩者都讓排隊中的
    // 那一則播不出來），唯獨這條路徑只有它守得住：開錄失敗時收音狀態立刻放開，
    // 若佇列沒被清空，drain 會接著把排隊中的那幾則播出來——長輩剛被告知「麥克風
    // 打不開」，緊接著卻聽到一段舊回覆。
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

  it("長輩插嘴時，還沒播到那幾則的音檔記憶體要回收，正在播的那一則不可回收", async () => {
    // ⚠️ Task 4 留下的缺口（Important 5 的剩下一半）：`queue.clear()` 只把項目
    // 從佇列丟掉，那些 blob URL 一個都不會被回收——瀏覽器不會替你清，它不知道
    // 你不再需要它了。展示現場長輩插嘴是常態，一則語音數十到數百 KB。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1" });
    await waitFor(() => expect(h.player.played.length).toBe(1));
    act(() => h.view.result.current.pressIn());
    act(() => h.recorder.finishStart());
    // 傳的是「要留著的那一則」＝正在播的（src 還掛在播放器上）；其餘一律回收。
    await waitFor(() =>
      expect(h.revokeQueuedReplyAudio).toHaveBeenCalledWith("https://cdn.example/a.m4a"),
    );
  });
});

describe("分段續播", () => {
  it("回覆不只一段時會去取下一段", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1", chunk_count: 3 });
    await waitFor(() => expect(h.getTurnChunk).toHaveBeenCalledWith(1, "d1", "tok"));
  });

  it("只有一段時不去取，播完就回到待機", async () => {
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1", chunk_count: 1 });
    await waitFor(() => expect(h.player.played.length).toBe(1));
    await act(async () => {
      h.player.finish();
    });
    expect(h.getTurnChunk).not.toHaveBeenCalled();
    // 播完沒有下一段了，畫面要回到待機——停在「說話中」的話長輩會一直等他講完。
    expect(h.view.result.current.avatar).toBe("idle");
  });

  it("長輩在播放中又講一句時，上一輪的續拉要作廢", async () => {
    // ⚠️ 不作廢的話，新回覆的句子會被接在舊回覆後面播出去。
    const h = setup();
    await waitFor(() => expect(h.view.result.current.micReady).toBe(true));
    h.socket.open();
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t1", chunk_count: 3 });
    await waitFor(() => expect(h.getTurnChunk).toHaveBeenCalledTimes(1));
    // 新的一輪回覆進來，只有一段
    h.socket.emit({ ...REPLY, type: "reply", turn_id: "t2", reply_digest: "d2", chunk_count: 1 });
    await act(async () => {
      h.player.finish();
    });
    // 舊那一輪的第 2 段不可以被取
    expect(h.getTurnChunk).toHaveBeenCalledTimes(1);
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

  it("切回來時重新連線，長輩可以繼續講話", async () => {
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
