import { describe, expect, it, test } from "vitest";

import {
  createPlaybackQueue,
  createTalkSocket,
  playAndWait,
  type TalkFrame,
} from "./talkSocket";

/** 假的 WebSocket：手動控制開、收、關，不碰網路。 */
class FakeSocket {
  static instances: FakeSocket[] = [];
  readyState = 0;
  /** 瀏覽器真實預設值是 "blob"；程式若忘記把它設成 "arraybuffer"，測試才測得出來。 */
  binaryType = "blob";
  sent: (ArrayBuffer | string)[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }

  send(data: ArrayBuffer | string) {
    this.sent.push(data);
  }

  close() {
    this.closed = true;
    this.readyState = 3;
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  emit(frame: unknown) {
    this.onmessage?.({ data: typeof frame === "string" ? frame : JSON.stringify(frame) });
  }

  /** 明確送一則已序列化的文字訊框（網頁端差異測試專用）。 */
  emitText(data: string) {
    this.onmessage?.({ data });
  }

  drop() {
    this.readyState = 3;
    this.onclose?.();
  }
}

function setup(overrides: Partial<Parameters<typeof createTalkSocket>[0]> = {}) {
  FakeSocket.instances = [];
  const frames: TalkFrame[] = [];
  const statuses: string[] = [];
  const timers: (() => void)[] = [];
  const socket = createTalkSocket({
    baseUrl: "http://backend.test",
    token: "tok-1",
    onFrame: (f) => frames.push(f),
    onStatus: (s) => statuses.push(s),
    createSocket: (url) => new FakeSocket(url) as unknown as WebSocket,
    setTimeoutFn: (fn) => {
      timers.push(fn);
      return timers.length - 1;
    },
    clearTimeoutFn: () => {},
    ...overrides,
  });
  return { socket, frames, statuses, timers, sockets: FakeSocket.instances };
}

describe("talkSocket 連線", () => {
  test("http 端點轉成 ws，token 走 query string（RN 握手不能自訂標頭）", () => {
    const { sockets } = setup();
    expect(sockets[0].url).toBe("ws://backend.test/api/v1/ws/talk?token=tok-1");
  });

  test("token 有特殊字元時會被編碼", () => {
    FakeSocket.instances = [];
    createTalkSocket({
      baseUrl: "https://backend.test/",
      token: "a b&c",
      onFrame: () => {},
      createSocket: (url) => new FakeSocket(url) as unknown as WebSocket,
    });
    expect(FakeSocket.instances[0].url).toBe(
      "wss://backend.test/api/v1/ws/talk?token=a%20b%26c",
    );
  });

  test("下行訊框原樣交出去", () => {
    const { frames, sockets } = setup();
    sockets[0].open();
    sockets[0].emit({ type: "ack", turn_id: "t1", text: "好，我幫您查一下喔", audio_url: "u", duration_ms: 1300 });
    sockets[0].emit({ type: "reply", turn_id: "t1", text: "今天三則新聞", audio_url: "v", duration_ms: 3000, chunk_count: 0, reply_digest: "" });
    expect(frames.map((f) => f.type)).toEqual(["ack", "reply"]);
  });

  test("壞掉的訊框只丟掉那一則，不影響後續", () => {
    const { frames, sockets } = setup();
    sockets[0].open();
    sockets[0].emit("這不是 JSON {{{");
    sockets[0].emit({ type: "error", turn_id: "t1", text: "金孫這邊有點小狀況" });
    expect(frames).toHaveLength(1);
    expect(frames[0].type).toBe("error");
  });
});

describe("talkSocket 送出", () => {
  test("連線開了就直接送", () => {
    const { socket, sockets } = setup();
    sockets[0].open();
    const audio = new ArrayBuffer(8);
    socket.sendAudio(audio);
    expect(sockets[0].sent).toEqual([audio]);
  });

  test("⭐ 連線還沒開時先擱著，開了自動補送——長輩不會再講第二次", () => {
    const { socket, sockets } = setup();
    const audio = new ArrayBuffer(8);
    socket.sendAudio(audio);
    expect(sockets[0].sent).toEqual([]);
    expect(socket.pendingCount()).toBe(1);
    sockets[0].open();
    expect(sockets[0].sent).toEqual([audio]);
    expect(socket.pendingCount()).toBe(0);
  });

  // ⚠️ 斷言的是**線路上的鍵名**，不是本地型別的欄位名。原本這裡照抄 ElderPlace 的
  // `place`，於是它與後端讀的 `location` 對不起來也全綠——2026-07-28 對講機改走
  // WebSocket 後位置整整幾小時沒寫進庫，金孫每次都反問「您人在哪裡」，就是這條測試
  // 斷言錯了東西放過去的。鍵名見 docs/dev/06_API設計規範.md 的 WS 上行契約。
  test("位置以 JSON 送出，鍵名照 WS 契約用 location；null＝這輪沒有位置，不送", () => {
    const { socket, sockets } = setup();
    sockets[0].open();
    socket.sendLocation(null);
    expect(sockets[0].sent).toEqual([]);
    socket.sendLocation({ place: "台南市", latitude: 22.99, longitude: 120.21 });
    expect(JSON.parse(sockets[0].sent[0] as string)).toEqual({
      location: "台南市",
      latitude: 22.99,
      longitude: 120.21,
    });
  });
});

describe("talkSocket 重連", () => {
  test("斷線會排重連，且退避時間逐次拉長", () => {
    const delays: number[] = [];
    const { sockets } = setup({
      setTimeoutFn: (fn, ms) => {
        delays.push(ms);
        fn(); // 立刻重連，模擬時間到
        return 0;
      },
    });
    sockets[0].open();
    sockets[0].drop();
    sockets[1].drop();
    sockets[2].drop();
    expect(delays).toEqual([500, 1000, 2000]);
  });

  test("重連成功後退避重新歸零——長時間使用不會越拖越久", () => {
    const delays: number[] = [];
    const { sockets } = setup({
      setTimeoutFn: (fn, ms) => {
        delays.push(ms);
        fn();
        return 0;
      },
    });
    sockets[0].open();
    sockets[0].drop();
    sockets[1].open(); // 這次連上了
    sockets[1].drop();
    expect(delays).toEqual([500, 500]);
  });

  test("自己關掉就不重連", () => {
    const { socket, sockets } = setup();
    sockets[0].open();
    socket.close();
    sockets[0].drop();
    expect(sockets).toHaveLength(1);
  });
});

describe("playbackQueue 播放佇列", () => {
  const item = (turnId: string) => ({
    turnId,
    audioUrl: `${turnId}.m4a`,
    text: turnId,
    durationMs: 0,
  });

  test("⭐ 一次只播一則，先到先播——聲音是線性的，同時播長輩什麼都聽不懂", async () => {
    const played: string[] = [];
    let inFlight = 0;
    let maxInFlight = 0;
    const queue = createPlaybackQueue(async (i) => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await Promise.resolve();
      played.push(i.turnId);
      inFlight -= 1;
    });
    queue.push(item("a"));
    queue.push(item("b"));
    queue.push(item("c"));
    await new Promise((r) => setTimeout(r, 0));
    expect(played).toEqual(["a", "b", "c"]);
    expect(maxInFlight).toBe(1);
  });

  test("一則播不出來就跳過下一則，不可讓整條佇列卡死", async () => {
    const played: string[] = [];
    const queue = createPlaybackQueue(async (i) => {
      if (i.turnId === "b") throw new Error("播不出來");
      played.push(i.turnId);
    });
    queue.push(item("a"));
    queue.push(item("b"));
    queue.push(item("c"));
    await new Promise((r) => setTimeout(r, 0));
    expect(played).toEqual(["a", "c"]);
  });

  test("長輩開口就清空還沒播的——不然金孫的聲音會被錄進去", async () => {
    const played: string[] = [];
    const queue = createPlaybackQueue(async (i) => {
      played.push(i.turnId);
      await new Promise((r) => setTimeout(r, 5));
    });
    queue.push(item("a"));
    queue.push(item("b"));
    queue.push(item("c"));
    queue.clear();
    await new Promise((r) => setTimeout(r, 30));
    expect(played).toEqual(["a"]);
    expect(queue.size()).toBe(0);
  });
});

describe("playAndWait 等一則播完", () => {
  const item = { turnId: "t1", audioUrl: "a.m4a", text: "好", durationMs: 1000 };

  function fakePlayer() {
    const listeners: ((s: { didJustFinish: boolean }) => void)[] = [];
    let removed = 0;
    return {
      calls: [] as string[],
      removedCount: () => removed,
      listenerCount: () => listeners.length,
      emit(didJustFinish: boolean) {
        for (const l of [...listeners]) l({ didJustFinish });
      },
      addListener(_event: "playbackStatusUpdate", cb: (s: { didJustFinish: boolean }) => void) {
        listeners.push(cb);
        return {
          remove: () => {
            removed += 1;
            const i = listeners.indexOf(cb);
            if (i >= 0) listeners.splice(i, 1);
          },
        };
      },
      replace(source: { uri: string }) {
        this.calls.push(`replace:${source.uri}`);
      },
      play() {
        this.calls.push("play");
      },
    };
  }

  test("⭐ 監聽在 replace／play 之前註冊——安撫話短到可能先播完", () => {
    const player = fakePlayer();
    const order: string[] = [];
    const spy = {
      ...player,
      addListener(e: "playbackStatusUpdate", cb: (s: { didJustFinish: boolean }) => void) {
        order.push("listen");
        return player.addListener(e, cb);
      },
      replace(source: { uri: string }) {
        order.push("replace");
        player.replace(source);
      },
      play() {
        order.push("play");
        player.play();
      },
    };
    void playAndWait(spy, item, { setTimeoutFn: () => 0 as never, clearTimeoutFn: () => {} });
    expect(order).toEqual(["listen", "replace", "play"]);
  });

  test("didJustFinish 才算播完；中途的狀態更新不放行", async () => {
    const player = fakePlayer();
    let resolved: string | null = null;
    const p = playAndWait(player, item, {
      setTimeoutFn: () => 0 as never,
      clearTimeoutFn: () => {},
    }).then((o) => (resolved = o));
    player.emit(false);
    await Promise.resolve();
    expect(resolved).toBeNull();
    player.emit(true);
    await p;
    expect(resolved).toBe("finished");
  });

  test("⭐ 事件沒來時保險逾時放行——否則整條佇列永遠卡死", async () => {
    const player = fakePlayer();
    const delays: number[] = [];
    let fire: (() => void) | null = null;
    const promise = playAndWait(player, item, {
      setTimeoutFn: (fn, ms) => {
        delays.push(ms);
        fire = fn;
        return 0 as never;
      },
      clearTimeoutFn: () => {},
      guardMs: 3000,
    });
    expect(delays).toEqual([4000]); // 該段時長 1000 ＋ 保險 3000
    fire!(); // 保險到期
    await expect(promise).resolves.toBe("timeout");
  });

  test("播完後一定解除訂閱，且只解除一次", async () => {
    const player = fakePlayer();
    const p = playAndWait(player, item, {
      setTimeoutFn: () => 0 as never,
      clearTimeoutFn: () => {},
    });
    player.emit(true);
    player.emit(true); // 重複事件不該重複解除
    await p;
    expect(player.removedCount()).toBe(1);
    expect(player.listenerCount()).toBe(0);
  });
});

/**
 * 網頁端的三處差異（spec §8.2，2026-07-30 實測）。
 *
 * 這三條是 App 版本沒有、也不可能有的——它們是瀏覽器與 React Native 的行為差異。
 */

describe("網頁端差異", () => {
  it("建立連線後把 binaryType 設成 arraybuffer", () => {
    let created: FakeSocket | null = null;
    createTalkSocket({
      baseUrl: "http://x",
      token: "t",
      onFrame: () => undefined,
      createSocket: (url) => {
        created = new FakeSocket(url);
        return created as unknown as WebSocket;
      },
    });
    expect((created as unknown as { binaryType: string }).binaryType).toBe("arraybuffer");
  });

  it("收到排隊訊框時原樣交給呼叫端", () => {
    const frames: unknown[] = [];
    let socket: FakeSocket | null = null;
    createTalkSocket({
      baseUrl: "http://x",
      token: "t",
      onFrame: (frame) => frames.push(frame),
      createSocket: (url) => {
        socket = new FakeSocket(url);
        return socket as unknown as WebSocket;
      },
    });
    (socket as unknown as FakeSocket).emitText(
      JSON.stringify({ type: "queued", turn_id: "t1", position: 2 }),
    );
    // ⚠️ 期望值宣告成有型別的 TalkFrame 常數（審查回合二 Important）：onFrame 的
    // 轉發邏輯本就不檢查 type 字面值是否落在聯集內，光靠執行期斷言測不出
    // `queued` 聯集成員被誰無聲刪掉——刪掉後這裡會變成 TS2322，typecheck 這道
    // gate 會先紅，而不必等到有人真的寫 `case "queued":` 才發現契約鏡射不見了。
    const expected: TalkFrame = { type: "queued", turn_id: "t1", position: 2 };
    expect(frames).toEqual([expected]);
  });
});
