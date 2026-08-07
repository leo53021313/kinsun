/**
 * 對講機的 WebSocket 客戶端（spec 2026-07-28 P2）。
 *
 * 為什麼整輪走 WebSocket 而不是照舊 POST：後端要能**主動**送第二則訊息——先「好，
 * 我幫您查一下喔」，答案好了再送。而後端跑兩個 worker，只加下行通道會讓「算出答案的
 * worker 推不到長輩的連線」；整輪同一條連線讓歸屬問題自動消失。
 *
 * 這個模組刻意**不碰音訊播放與 React**：它只管連線、送出、把下行訊框交出去，
 * 所以可以完全離線單元測試（見 talkSocket.test.ts）。播放順序由 createPlaybackQueue
 * 負責，同樣是純資料結構。
 */

/** 後端下行訊框。三種型別共用 turn_id，App 端據此對應是哪一輪。 */
export type TalkFrame =
  | {
      type: "ack";
      turn_id: string;
      text: string;
      audio_url: string;
      duration_ms: number;
    }
  | {
      type: "reply";
      turn_id: string;
      text: string;
      audio_url: string;
      duration_ms: number | null;
      chunk_count: number;
      reply_digest: string;
    }
  | { type: "error"; turn_id: string; text: string };

/**
 * `setTimeout` 的回傳值在 RN／瀏覽器是 number，載入 Node 型別時則是 Timeout。
 *
 * 兩種宣告在不同作業系統的多載排序不一致，不能用單一 ReturnType 代表所有建置環境；
 * 此值只會原樣交回 clearTimeout，因此保留聯集、不讀取其內部欄位。
 */
export type RetryHandle = number | ReturnType<typeof setTimeout>;

/**
 * 把 WS 收到的 binary 訊框正規化成 ArrayBuffer。
 *
 * RN 兩平台的 binary 訊框都是 `ArrayBuffer`（`react-native` 的
 * `Libraries/WebSocket/WebSocket.js` 對 `type: 'binary'` 走
 * `base64.toByteArray(ev.data).buffer`，而 iOS／Android 原生端一律送 `'binary'`）。
 * `binaryType` 預設是 `undefined`——與瀏覽器預設 `"blob"` 不同，本專案不設，故永遠
 * 拿到 ArrayBuffer。TypedArray 那一支只是防禦性處理，不是預期路徑。
 */
export function asArrayBuffer(data: unknown): ArrayBuffer | null {
  if (data instanceof ArrayBuffer) {
    return data;
  }
  if (ArrayBuffer.isView(data)) {
    const view = data as ArrayBufferView;
    return view.buffer.slice(view.byteOffset, view.byteOffset + view.byteLength) as ArrayBuffer;
  }
  return null;
}

/**
 * 解析內嵌音檔的回覆訊框（2026-07-30 延遲優化 C1）。
 *
 * 格式：`[4 bytes 大端序 header 長度][UTF-8 JSON header][m4a bytes]`，header 的欄位
 * 與 JSON `reply` 訊框完全相同。
 *
 * ⚠️ **為什麼 header 要嵌在同一個訊框裡，而不是「先收 JSON 再收 binary」**：後端同一條
 * 連線最多三輪併發，兩輪幾乎同時算完時「JSON(A)、JSON(B)、binary(A)、binary(B)」的
 * 交錯完全可能——靠順序配對就會把 A 的音檔配上 B 的字幕。自我描述的訊框對交錯免疫。
 *
 * 壞訊框回 null（只丟這一則，不可切斷連線）：外部輸入是資料不是指令。
 */
export function parseAudioFrame(
  buffer: ArrayBuffer,
): { header: Record<string, unknown>; bytes: Uint8Array } | null {
  if (buffer.byteLength < 4) {
    return null;
  }
  const headerLength = new DataView(buffer).getUint32(0, false);
  if (headerLength === 0 || 4 + headerLength > buffer.byteLength) {
    return null;
  }
  let header: unknown;
  try {
    header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 4, headerLength)));
  } catch {
    return null;
  }
  if (!header || typeof header !== "object" || Array.isArray(header)) {
    return null;
  }
  const fields = header as Record<string, unknown>;
  if (typeof fields.turn_id !== "string") {
    return null;
  }
  return { header: fields, bytes: new Uint8Array(buffer, 4 + headerLength) };
}

export type TalkSocketStatus = "connecting" | "open" | "closed";

export type ElderPlace = {
  place: string;
  latitude: number;
  longitude: number;
};

type TalkSocketOptions = {
  baseUrl: string;
  token: string;
  onFrame: (frame: TalkFrame) => void;
  onStatus?: (status: TalkSocketStatus) => void;
  /** 注入點：測試用假的 WebSocket，正式用全域的。 */
  createSocket?: (url: string) => WebSocket;
  /** 注入點：測試不想真的等。RetryHandle 讓兩個注入點的型別對得起來。 */
  setTimeoutFn?: (fn: () => void, ms: number) => RetryHandle;
  clearTimeoutFn?: (handle: RetryHandle) => void;
  /**
   * 注入點：把內嵌音檔的位元組落地成可播放的 uri（正式用
   * `replyAudio.writeReplyAudio`，見該模組說明為什麼不在這裡直接 import）。
   *
   * 未提供＝收到 binary 訊框只能丟掉（本模組不知道怎麼播音檔）。這也是離線單元測試
   * 的預設狀態：協定解析測得到，檔案系統碰不到。
   */
  writeAudio?: (bytes: Uint8Array) => { uri: string };
};

/**
 * 重連退避（毫秒）。第一次幾乎立刻重試——長輩不會知道「連線斷了」是什麼意思，
 * 他只會看到金孫突然不理他。後面拉長是為了不要在真的沒網路時狂打。
 */
const RECONNECT_DELAYS_MS = [500, 1000, 2000, 5000, 10000];

/** token 走 query string：WebSocket 握手在 React Native 與瀏覽器都不能自訂標頭。 */
function talkUrl(baseUrl: string, token: string): string {
  const base = baseUrl.replace(/^http/, "ws").replace(/\/+$/, "");
  return `${base}/api/v1/ws/talk?token=${encodeURIComponent(token)}`;
}

export function createTalkSocket(options: TalkSocketOptions) {
  const {
    baseUrl,
    token,
    onFrame,
    onStatus,
    createSocket = (url: string) => new WebSocket(url),
    setTimeoutFn = setTimeout,
    clearTimeoutFn = clearTimeout,
    writeAudio,
  } = options;

  let socket: WebSocket | null = null;
  let attempt = 0;
  let closedByUs = false;
  let retryHandle: RetryHandle | null = null;
  // 連線還沒開時先擱著，開了再補送。長輩按住麥克風的那一刻不該因為連線在重連而失去
  // 那句話——他不會再講第二次。
  let queued: (ArrayBuffer | string)[] = [];

  function setStatus(status: TalkSocketStatus) {
    onStatus?.(status);
  }

  function flush() {
    if (!socket || socket.readyState !== 1) return;
    const pending = queued;
    queued = [];
    for (const item of pending) socket.send(item as never);
  }

  function connect() {
    if (closedByUs) return;
    setStatus("connecting");
    const next = createSocket(talkUrl(baseUrl, token));
    socket = next;

    next.onopen = () => {
      attempt = 0;
      setStatus("open");
      flush();
    };

    next.onmessage = (event: { data: unknown }) => {
      if (typeof event.data === "string") {
        let frame: TalkFrame;
        try {
          frame = JSON.parse(event.data);
        } catch {
          // 壞掉的訊框只丟掉這一則，不可讓它切斷連線（外部輸入是資料不是指令）。
          return;
        }
        if (frame && typeof frame === "object" && "type" in frame) onFrame(frame);
        return;
      }
      // 內嵌音檔的回覆訊框（C1）：落地成本地檔之後，當成一則**普通的 reply**交出去
      // ——`audio_url` 換成 `file://…`，呼叫端（含分段續拉的整套邏輯）一行都不必改。
      const buffer = asArrayBuffer(event.data);
      if (!buffer || !writeAudio) return;
      const parsed = parseAudioFrame(buffer);
      if (!parsed) return;
      let uri: string;
      try {
        uri = writeAudio(parsed.bytes).uri;
      } catch {
        // 落地失敗＝這一則沒有聲音。刻意仍把 frame 交出去（`audio_url` 留空）：
        // 字幕與分段資訊照樣有用，長輩至少看得到字、續拉還能繼續。
        onFrame({ ...parsed.header, audio_url: "" } as unknown as TalkFrame);
        return;
      }
      onFrame({ ...parsed.header, audio_url: uri } as unknown as TalkFrame);
    };

    next.onclose = () => {
      setStatus("closed");
      if (closedByUs) return;
      const delay = RECONNECT_DELAYS_MS[Math.min(attempt, RECONNECT_DELAYS_MS.length - 1)];
      attempt += 1;
      retryHandle = setTimeoutFn(connect, delay);
    };

    // onerror 不另外處理：瀏覽器與 RN 都會在 error 之後緊接著發 close，
    // 兩邊都排重連會變成一次斷線重連兩次。
    next.onerror = () => {};
  }

  connect();

  return {
    /** 送一輪的音檔。連線還沒開就先擱著，開了自動補送。 */
    sendAudio(audio: ArrayBuffer) {
      queued.push(audio);
      flush();
    },
    /**
     * 更新「下一輪要用的位置」。null＝這輪沒有位置，不送（不是「他不在任何地方」）。
     *
     * ⚠️ 地名的鍵名是 `location` 而非本地型別的 `place`：線路契約由後端與
     * `POST /turns` 的表單欄位定義（見 docs/dev/06_API設計規範.md），不可直接
     * `JSON.stringify(place)` 把本地欄位名送上去——那正是 2026-07-28 的故障：
     * 後端 `_parse_location` 讀不到 `location`，位置一列都沒寫進庫，金孫從此
     * 每次問地點都反問「您人在哪裡」。
     */
    sendLocation(place: ElderPlace | null) {
      if (!place) return;
      queued.push(
        JSON.stringify({
          location: place.place,
          latitude: place.latitude,
          longitude: place.longitude,
        }),
      );
      flush();
    },
    close() {
      closedByUs = true;
      if (retryHandle !== null) clearTimeoutFn(retryHandle);
      socket?.close();
    },
    /** 測試與除錯用。 */
    pendingCount() {
      return queued.length;
    },
  };
}

export type PlaybackItem = {
  /** 安撫語音播完仍在等待答案；正式回覆播完才可回到待機。 */
  kind: "ack" | "reply";
  turnId: string;
  audioUrl: string;
  text: string;
  /** 這一段語音多長（毫秒）。播放端據此知道何時可以放下一則。 */
  durationMs: number;
};

/**
 * 播放器的最小介面（只取本模組真的用到的三個方法）。
 *
 * 對 `expo-audio` 的 `AudioPlayer` 結構相容，但不 import 它——這樣等待邏輯可以
 * 完全離線單元測試，不必在測試裡拉起音訊模組。
 */
export type PlayerLike = {
  addListener(
    event: "playbackStatusUpdate",
    listener: (status: { didJustFinish: boolean }) => void,
  ): { remove(): void };
  replace(source: { uri: string }): void;
  play(): void;
};

/** 一則播完的原因：正常結束，或保險逾時（事件沒來）。 */
export type PlaybackOutcome = "finished" | "timeout";

/** 事件沒來時的保險額度（毫秒）：在該段時長之外再等這麼久就放行。 */
const PLAYBACK_GUARD_MS = 3000;

/**
 * 播一則並等它真的播完。
 *
 * ⚠️ **以 `didJustFinish` 事件為準，不用時長估算**（2026-07-28 修正）：時長雖然由
 * TTS 服務量測後隨訊框帶回來、數字本身可信，但「音檔多長」不等於「播完了」——
 * 載入、緩衝、iOS 音訊工作階段被搶走都會讓實際播放時間長於時長。估短了會讓下一則
 * 蓋掉還在講的這一則，長輩聽到的話會被砍頭。
 *
 * ⚠️ **監聽必須在 `replace`／`play` 之前註冊**：安撫話只有九到十個字，短到可能在
 * 註冊完成之前就播完，那一則的 `didJustFinish` 就永遠等不到。
 *
 * ⚠️ **保險逾時不可省**：事件真的沒來時（格式壞掉、音訊工作階段被錄音搶走），
 * 沒有保險就是整條佇列永遠卡死、長輩後面問的每一句都不會有回應。故以「該段時長
 * ＋三秒」為上限強制放行——寧可提早一點點，不可完全不動。
 */
export function playAndWait(
  player: PlayerLike,
  item: PlaybackItem,
  options: {
    setTimeoutFn?: (fn: () => void, ms: number) => RetryHandle;
    clearTimeoutFn?: (handle: RetryHandle) => void;
    guardMs?: number;
  } = {},
): Promise<PlaybackOutcome> {
  const {
    setTimeoutFn = setTimeout,
    clearTimeoutFn = clearTimeout,
    guardMs = PLAYBACK_GUARD_MS,
  } = options;
  return new Promise<PlaybackOutcome>((resolve) => {
    let settled = false;
    let guard: RetryHandle | null = null;
    const finish = (outcome: PlaybackOutcome) => {
      if (settled) return;
      settled = true;
      subscription.remove();
      if (guard !== null) clearTimeoutFn(guard);
      resolve(outcome);
    };
    const subscription = player.addListener("playbackStatusUpdate", (status) => {
      if (status.didJustFinish) finish("finished");
    });
    guard = setTimeoutFn(() => finish("timeout"), item.durationMs + guardMs);
    player.replace({ uri: item.audioUrl });
    player.play();
  });
}

/**
 * 播放佇列：一次只播一則，先到先播。
 *
 * ⚠️ 為什麼需要它（spec 2026-07-28）：非同步回覆下，一輪會產生兩則語音（安撫話、
 * 答案），而長輩連問兩件事時還會有兩輪交錯回來。同時播兩則的話長輩什麼都聽不懂——
 * 聲音是線性的，不像畫面可以並排。
 *
 * ⚠️ 長輩按住麥克風時要 `clear()`：對講機模式下按下去就是要講話，不停掉正在播的
 * 會把金孫的聲音錄進去。
 */
export function createPlaybackQueue(play: (item: PlaybackItem) => Promise<void>) {
  const items: PlaybackItem[] = [];
  let running = false;

  async function drain() {
    if (running) return;
    running = true;
    try {
      while (items.length > 0) {
        const next = items.shift()!;
        try {
          await play(next);
        } catch {
          // 一則播不出來就跳過下一則，不可讓整條佇列卡死——長輩會以為金孫沒回答。
        }
      }
    } finally {
      running = false;
    }
  }

  return {
    push(item: PlaybackItem) {
      items.push(item);
      void drain();
    },
    /** 長輩開口了：丟掉還沒播的。正在播的那一則由呼叫端自己停。 */
    clear() {
      items.length = 0;
    },
    size() {
      return items.length;
    },
    isPlaying() {
      return running;
    },
  };
}
