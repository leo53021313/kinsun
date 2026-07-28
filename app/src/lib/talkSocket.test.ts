import { createPlaybackQueue, createTalkSocket, type TalkFrame } from "./talkSocket";

/** 假的 WebSocket：手動控制開、收、關，不碰網路。 */
class FakeSocket {
  static instances: FakeSocket[] = [];
  readyState = 0;
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

  test("位置以 JSON 送出；null＝這輪沒有位置，不送", () => {
    const { socket, sockets } = setup();
    sockets[0].open();
    socket.sendLocation(null);
    expect(sockets[0].sent).toEqual([]);
    socket.sendLocation({ place: "台南市", latitude: 22.99, longitude: 120.21 });
    expect(JSON.parse(sockets[0].sent[0] as string)).toEqual({
      place: "台南市",
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
  const item = (turnId: string) => ({ turnId, audioUrl: `${turnId}.m4a`, text: turnId });

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
