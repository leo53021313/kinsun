/**
 * 阿白 renderer 的版本化 bridge 協定（三端共用，✅ D-51）。
 *
 * 2026-08-09 由 `app/src/lib/ottoBridge.ts` 搬來：網頁版 W3 要載入同一份
 * `renderer.html`，協定若在 web 那側另寫一份，兩份的欄位裁切與版本檢查就會各自
 * 演化——而 renderer 只有一份，對不上時的症狀是「阿白不動」而不是編譯錯誤。
 *
 * ⚠️ 這裡刻意宣告自己的 `OttoVisualState`，不從 app 的 `talkPresentation` 匯入：
 * 那支是接手指示第 11 條點名不准動的狀態機檔案，而 `shared/` 也不該反向依賴任何
 * 一端。兩者是同一組五個名稱，app 端以型別相容性（`ottoBridge.test.ts` 有一條
 * 編譯期斷言）確保不會漂。
 */

/** 對講機的五個視覺狀態。名稱與時機完全沿用既有狀態機，此處只是協定的一份宣告。 */
export type OttoVisualState = "idle" | "listening" | "thinking" | "speaking" | "error";

export const OTTO_BRIDGE_VERSION = 1 as const;

export type OttoSpeechCue = {
  /** 每一段實際播放都要有不同 key，確保同文案重播時仍重新對嘴。 */
  key: string;
  text: string;
  durationMs: number;
  emotion?: string | null;
};

export type OttoSyncCommand = {
  version: typeof OTTO_BRIDGE_VERSION;
  type: "sync";
  sequence: number;
  state: OttoVisualState;
  text?: string;
  durationMs?: number;
  emotion?: string;
};

/**
 * 視線指令：讓阿白的眼睛與頭轉向某個方向。
 *
 * ⚠️ **刻意不走 `sync` 的單調序號**：指標每動一下就是一則，序號去重會讓兩種指令
 * 互相擋掉（視線把序號推高，狀態指令就進不去了）。視線是冪等的——丟掉幾則只是
 * 少幾格平滑，而 `sync` 掉一則會讓阿白停在錯的狀態，兩者的容錯要求不同。
 */
export type OttoLookCommand = {
  version: typeof OTTO_BRIDGE_VERSION;
  type: "look";
  /** -1（左／上）到 1（右／下）；`null` 代表回正（指標離開畫面）。 */
  x: number | null;
  y: number | null;
};

/**
 * 點了待機時浮出來的小道具（戳泡泡、餵他一條魚⋯）。
 *
 * ⚠️ 同樣不吃 `sequence`：重複點由 renderer 那側的 `Idle.tap()` 自己擋（一次待機
 * 只認第一下，連按不會把動作切斷重演），不需要外層再排一次序。
 */
export type OttoTapCommand = {
  version: typeof OTTO_BRIDGE_VERSION;
  type: "tap";
};

/** renderer 目前浮出來的可點道具；`x`／`y` 是**舞台百分比**（0–100）。 */
export type OttoIdleProp = {
  key: string;
  icon: string;
  label: string;
  zh: string;
  x: number;
  y: number;
};

export type OttoRendererEvent =
  | {
      version: typeof OTTO_BRIDGE_VERSION;
      type: "ready" | "invalid-message";
    }
  | {
      version: typeof OTTO_BRIDGE_VERSION;
      type: "idle-prop";
      /** `null`＝道具收起來了（被點過、或這段待機結束）。 */
      prop: OttoIdleProp | null;
    };

/**
 * 進畫面時揮手打招呼。
 *
 * ⚠️ **由呈現層主動送、不是 renderer 自己啟動時做**：「什麼時候該打招呼」只有應用層
 * 知道（長輩剛進對講機 vs. 只是切個頁籤回來），而 renderer 每次重新載入都自己打一次
 * 會變成雜訊。同樣不吃 `sequence`——它不是狀態，是一次性的演出。
 */
export type OttoGreetCommand = {
  version: typeof OTTO_BRIDGE_VERSION;
  type: "greet";
};

export function createOttoTapCommand(): OttoTapCommand {
  return { version: OTTO_BRIDGE_VERSION, type: "tap" };
}

export function createOttoGreetCommand(): OttoGreetCommand {
  return { version: OTTO_BRIDGE_VERSION, type: "greet" };
}

/** 兩軸要嘛都有效、要嘛一起回正——只有一軸的視線會讓阿白歪向一個沒人在的方向。 */
export function createOttoLookCommand(
  x: number | null,
  y: number | null,
): OttoLookCommand {
  const clamp = (v: number | null) =>
    v === null || !Number.isFinite(v) ? null : Math.min(1, Math.max(-1, v));
  const nx = clamp(x);
  const ny = clamp(y);
  const paired = nx !== null && ny !== null;
  return {
    version: OTTO_BRIDGE_VERSION,
    type: "look",
    x: paired ? nx : null,
    y: paired ? ny : null,
  };
}

export function createOttoSyncCommand(
  sequence: number,
  state: OttoVisualState,
  speechCue: OttoSpeechCue | null,
): OttoSyncCommand {
  const command: OttoSyncCommand = {
    version: OTTO_BRIDGE_VERSION,
    type: "sync",
    sequence,
    state,
  };
  if (state !== "speaking" || !speechCue) {
    return command;
  }
  command.text = speechCue.text.slice(0, 500);
  command.durationMs = Number.isFinite(speechCue.durationMs)
    ? Math.min(120_000, Math.max(0, Math.round(speechCue.durationMs)))
    : 0;
  if (speechCue.emotion) {
    command.emotion = speechCue.emotion;
  }
  return command;
}

export function parseOttoRendererEvent(data: string): OttoRendererEvent | null {
  let value: unknown;
  try {
    value = JSON.parse(data);
  } catch {
    return null;
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const event = value as Record<string, unknown>;
  if (event.version !== OTTO_BRIDGE_VERSION) {
    return null;
  }
  if (event.type === "ready" || event.type === "invalid-message") {
    return { version: OTTO_BRIDGE_VERSION, type: event.type };
  }
  if (event.type === "idle-prop") {
    // ⚠️ 傳輸欄位是 `detail`（renderer 那側 `notify(type, detail)` 的通用形狀），
    // 對外的欄位名是 `prop`——轉換在這裡做完，呈現層不必知道線上長什麼樣。
    return {
      version: OTTO_BRIDGE_VERSION,
      type: "idle-prop",
      prop: parseIdleProp(event.detail),
    };
  }
  return null;
}

/**
 * 把 renderer 送來的道具資料收成已知的形狀。
 *
 * ⚠️ 逐欄檢查而不是直接轉型：這是**跨越 iframe 邊界**進來的資料，即使 renderer 是
 * 我們自己的產物，呈現層仍會拿 `x`／`y` 直接當 CSS 位置、拿 `icon`／`label` 直接
 * 渲染。任何一欄不是預期型別就整包當作「沒有道具」，而不是讓 `NaN%` 或 `undefined`
 * 流進畫面。座標另外夾在 0–100：舞台外的道具長輩點不到，卻會撐開版面。
 */
function parseIdleProp(value: unknown): OttoIdleProp | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  const prop = value as Record<string, unknown>;
  const text = (field: unknown) =>
    typeof field === "string" && field.length > 0 && field.length <= 40 ? field : null;
  const key = text(prop.key);
  const icon = text(prop.icon);
  const label = text(prop.label);
  const zh = text(prop.zh);
  const x = Number(prop.x);
  const y = Number(prop.y);
  if (!key || !icon || !label || !zh || !Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }
  return {
    key,
    icon,
    label,
    zh,
    x: Math.min(100, Math.max(0, x)),
    y: Math.min(100, Math.max(0, y)),
  };
}
