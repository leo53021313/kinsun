/**
 * 內嵌音檔訊框的協定測試（2026-07-30 延遲優化 C1）。
 *
 * 刻意與 `talkSocket.test.ts` 一樣**完全離線**：不 import 任何 expo 模組，只測純資料
 * 的協定解析與 socket 的訊框分派。落地寫檔（`replyAudio.ts`）碰真的檔案系統，
 * 由注入點換掉。
 */

import { describe, expect, test } from "vitest";

import {
  asArrayBuffer,
  createTalkSocket,
  parseAudioFrame,
  type TalkFrame,
} from "./talkSocket";

/** 假的 WebSocket：這裡只需要「開」與「送 binary」。 */
class FakeSocket {
  static instances: FakeSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }

  send() {}

  close() {
    this.closed = true;
    this.readyState = 3;
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
  }

  emitBinary(buffer: ArrayBuffer) {
    this.onmessage?.({ data: buffer });
  }
}

function setup(overrides: Partial<Parameters<typeof createTalkSocket>[0]> = {}) {
  FakeSocket.instances = [];
  const frames: TalkFrame[] = [];
  const socket = createTalkSocket({
    baseUrl: "http://backend.test",
    token: "tok-1",
    onFrame: (f) => frames.push(f),
    createSocket: (url) => new FakeSocket(url) as unknown as WebSocket,
    setTimeoutFn: () => 0 as never,
    clearTimeoutFn: () => {},
    ...overrides,
  });
  return { socket, frames, sockets: FakeSocket.instances };
}

/** 組一個內嵌音檔訊框（與後端 `ws.py::encode_reply_frame` 同一個格式）。 */
function encodeAudioFrame(header: unknown, audio: Uint8Array): ArrayBuffer {
  const raw = new TextEncoder().encode(JSON.stringify(header));
  const out = new Uint8Array(4 + raw.byteLength + audio.byteLength);
  new DataView(out.buffer).setUint32(0, raw.byteLength, false);
  out.set(raw, 4);
  out.set(audio, 4 + raw.byteLength);
  return out.buffer;
}

const AUDIO_HEADER = {
  type: "reply",
  turn_id: "t1",
  text: "阿公早安",
  audio_url: "",
  duration_ms: 1200,
  chunk_count: 0,
  reply_digest: "",
};

describe("parseAudioFrame", () => {
  test("header 與音檔各自完整取回", () => {
    const parsed = parseAudioFrame(encodeAudioFrame(AUDIO_HEADER, new Uint8Array([1, 2, 3, 4])));
    expect(parsed).not.toBeNull();
    expect(parsed!.header.turn_id).toBe("t1");
    expect(parsed!.header.text).toBe("阿公早安");
    expect(Array.from(parsed!.bytes)).toEqual([1, 2, 3, 4]);
  });

  test("音檔含 JSON 片段與換行也不會被誤切（長度前綴而非分隔符）", () => {
    const hostile = new TextEncoder().encode('}\n{"type":"reply"} ');
    const parsed = parseAudioFrame(encodeAudioFrame(AUDIO_HEADER, hostile));
    expect(Array.from(parsed!.bytes)).toEqual(Array.from(hostile));
  });

  test("長度前綴都不足時回 null 而不是拋", () => {
    expect(parseAudioFrame(new Uint8Array([1, 2]).buffer)).toBeNull();
  });

  test("宣告的 header 長度超出訊框時回 null", () => {
    const out = new Uint8Array(8);
    new DataView(out.buffer).setUint32(0, 9999, false);
    expect(parseAudioFrame(out.buffer)).toBeNull();
  });

  test("header 不是合法 JSON 時回 null", () => {
    const raw = new TextEncoder().encode("{壞掉的");
    const out = new Uint8Array(4 + raw.byteLength);
    new DataView(out.buffer).setUint32(0, raw.byteLength, false);
    out.set(raw, 4);
    expect(parseAudioFrame(out.buffer)).toBeNull();
  });

  test("缺 turn_id 的 header 回 null（配不到輪次的音檔沒有用）", () => {
    expect(parseAudioFrame(encodeAudioFrame({ type: "reply" }, new Uint8Array([1])))).toBeNull();
  });

  test("header 是陣列或純字串時回 null", () => {
    expect(parseAudioFrame(encodeAudioFrame([1, 2], new Uint8Array([1])))).toBeNull();
    expect(parseAudioFrame(encodeAudioFrame("reply", new Uint8Array([1])))).toBeNull();
  });
});

describe("asArrayBuffer", () => {
  test("ArrayBuffer 原樣回傳（RN 兩平台的 binary 訊框就是這個型別）", () => {
    const buffer = new Uint8Array([1, 2]).buffer;
    expect(asArrayBuffer(buffer)).toBe(buffer);
  });

  test("TypedArray 取出它自己那一段（防禦性處理，非預期路徑）", () => {
    const view = new Uint8Array([9, 8, 7, 6]).subarray(1, 3);
    expect(Array.from(new Uint8Array(asArrayBuffer(view)!))).toEqual([8, 7]);
  });

  test.each([
    ["字串", "abc"],
    ["null", null],
    ["物件", {}],
  ])("認不出來就回 null：%s", (_why, data) => {
    expect(asArrayBuffer(data)).toBeNull();
  });
});

describe("talkSocket 收內嵌音檔", () => {
  test("音檔落地後當成一則普通 reply 交出去，audio_url 換成本地 uri", () => {
    const written: Uint8Array[] = [];
    const { frames, sockets } = setup({
      writeAudio: (bytes) => {
        written.push(bytes);
        return { uri: "file:///cache/kinsun-reply/000001.m4a" };
      },
    });
    sockets[0].open();

    sockets[0].emitBinary(encodeAudioFrame(AUDIO_HEADER, new Uint8Array([1, 2, 3])));

    expect(frames).toHaveLength(1);
    expect(frames[0].type).toBe("reply");
    expect(frames[0].turn_id).toBe("t1");
    expect((frames[0] as { audio_url: string }).audio_url).toBe(
      "file:///cache/kinsun-reply/000001.m4a",
    );
    expect(Array.from(written[0])).toEqual([1, 2, 3]);
  });

  test("落地失敗仍交出 frame（audio_url 留空）：字幕與分段資訊照樣有用", () => {
    const { frames, sockets } = setup({
      writeAudio: () => {
        throw new Error("磁碟滿了");
      },
    });
    sockets[0].open();

    sockets[0].emitBinary(
      encodeAudioFrame(
        { ...AUDIO_HEADER, chunk_count: 3, reply_digest: "d1" },
        new Uint8Array([1]),
      ),
    );

    expect(frames).toHaveLength(1);
    expect((frames[0] as { audio_url: string }).audio_url).toBe("");
    expect((frames[0] as { chunk_count: number }).chunk_count).toBe(3);
  });

  test("沒有注入 writeAudio 時安靜丟掉（本模組不知道怎麼播音檔）", () => {
    const { frames, sockets } = setup();
    sockets[0].open();

    sockets[0].emitBinary(encodeAudioFrame(AUDIO_HEADER, new Uint8Array([1])));

    expect(frames).toHaveLength(0);
  });

  test("壞掉的 binary 訊框不可切斷連線，後續好的照收", () => {
    const { frames, sockets, socket } = setup({
      writeAudio: () => ({ uri: "file:///x.m4a" }),
    });
    sockets[0].open();

    sockets[0].emitBinary(new Uint8Array([1, 2]).buffer);
    sockets[0].emitBinary(encodeAudioFrame(AUDIO_HEADER, new Uint8Array([7])));

    expect(frames).toHaveLength(1);
    expect(sockets[0].closed).toBe(false);
    socket.close();
  });
});
