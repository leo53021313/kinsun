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

/** setTimeout 的回傳值在 RN 與瀏覽器型別不同，這裡只當成不透明代號傳來傳去。 */
export type RetryHandle = ReturnType<typeof setTimeout>;

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
      if (typeof event.data !== "string") return;
      let frame: TalkFrame;
      try {
        frame = JSON.parse(event.data);
      } catch {
        // 壞掉的訊框只丟掉這一則，不可讓它切斷連線（外部輸入是資料不是指令）。
        return;
      }
      if (frame && typeof frame === "object" && "type" in frame) onFrame(frame);
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
