/**
 * 角色舞台與 renderer 的 bridge 接線。
 *
 * jsdom 不會真的執行 iframe 裡的 renderer，所以這裡驗的是**接線本身**：來源驗證、
 * ready 之後補送最後一個狀態、狀態改變時送新指令。renderer 內部的行為（黑名單、
 * 對嘴、SVG 啟動）由 `app/scripts/test-otto-runtime.mjs` 在真的跑起來的 DOM 上驗，
 * 兩邊不重複。
 */

import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// ⚠️ 讀的是**這一端真正會載入的那份產物**（`RENDERER_SRC` 指向它），不是
// `shared/otto-pet-core/sentiment.js` 來源：產物與來源一致由 `npm run build` 的
// `build-renderer.mjs --check` 守，這裡再往來源比對只是重複同一件事，而比對產物
// 才涵蓋「來源改了但沒重新產生」這個真實會發生的狀態。
// ⚠️ 用 `?raw` 而不是 `node:fs`：路徑由打包器解析，不依賴測試從哪個目錄啟動
//（jsdom 下 `import.meta.url` 不是 file: scheme，`fileURLToPath` 會擲例外）。
import rendererHtml from "../../public/otto/renderer.html?raw";
import { strings } from "@/strings";

import { BearStage } from "./BearStage";
import { BLOCKED_EMOTIONS, sanitizeEmotion } from "./bearEmotion";

function iframeWindow(): Window {
  const frame = document.querySelector("iframe");
  if (!frame?.contentWindow) throw new Error("找不到 renderer iframe");
  return frame.contentWindow;
}

/**
 * 模擬 renderer 送出 ready；來源刻意可換，用來驗來源檢查。
 *
 * ⚠️ 包在 `act` 裡：ready 會把 `isReady` 轉真，而視線追蹤的 effect 以它為相依
 * ——不 flush 的話監聽器根本還沒掛上，測試會以為「移動指標不送訊息」是實作壞了。
 */
function emitReady(source: Window | null) {
  act(() => {
    window.dispatchEvent(
      new MessageEvent("message", {
        data: JSON.stringify({ version: 1, type: "ready" }),
        source: source as MessageEventSource | null,
      }),
    );
  });
}

describe("BearStage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("舞台是純裝飾，狀態交給狀態帶的可見文字說（W3b 起）", () => {
    // W3a 期間這裡掛過 role="img" 與逐狀態的 aria-label，因為當時還沒有狀態帶，
    // 拿掉會讓看不見的長輩失去唯一線索。狀態帶到位後就換過去了——可見文字比
    // aria-label 好，看得見的人與聽的人拿到同一份資訊。狀態帶本身由
    // `TalkScreen.test.tsx` 驗。
    render(<BearStage state="listening" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    // ⚠️ 外層原本整塊 `aria-hidden`；2026-08-16 加入可點道具後改為**兩個裝飾層各自
    // 標記**——被祖先 `aria-hidden` 蓋住的按鈕，讀螢幕軟體看不到、鍵盤走到也讀不出
    // 東西。「純裝飾」這件事沒有變：沒有道具的時候，舞台裡一個可及的東西都沒有。
    expect(screen.getByTestId("bear-stage-glow")).toHaveAttribute("aria-hidden", "true");
    expect(document.querySelector("iframe")).toHaveAttribute("aria-hidden", "true");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    // iframe 仍要有 title：即使 aria-hidden，沒有可及名稱的 frame 是 a11y 稽核項。
    expect(document.querySelector("iframe")).toHaveAttribute(
      "title",
      strings.talk.companionTitle,
    );
  });

  it("光暈用該狀態的設計 token，不是寫死的顏色", () => {
    render(<BearStage state="thinking" />);
    const glow = screen.getByTestId("bear-stage-glow");
    expect(glow.style.background).toContain("--talk-thinking-glow");
  });

  it("舞台尺寸是核准的 209 × 300，不隨內容縮放", () => {
    render(<BearStage state="idle" />);
    const stage = screen.getByTestId("bear-stage");
    expect(stage.className).toContain("w-[var(--avatar-stage-w)]");
    expect(stage.className).toContain("h-[var(--avatar-stage-h)]");
  });

  it("收到自己 iframe 的 ready 之後，補送最後一個狀態", () => {
    render(<BearStage state="listening" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    expect(post).toHaveBeenCalledTimes(1);
    const [payload] = post.mock.calls[0];
    expect(JSON.parse(String(payload))).toMatchObject({
      version: 1,
      type: "sync",
      state: "listening",
    });
  });

  it("不是自己 iframe 送來的 ready 一律不理", () => {
    // 頁面上任何腳本（含瀏覽器擴充）都能對 window 送 message。不驗來源的話，
    // 別人的訊息就能把舞台騙進 ready，而真正的 renderer 還沒起來。
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(window);
    emitReady(null);
    expect(post).not.toHaveBeenCalled();
  });

  it("ready 之後狀態改變會送出新指令，且 sequence 遞增", () => {
    const { rerender } = render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    rerender(<BearStage state="speaking" />);

    const commands = post.mock.calls.map((call) => JSON.parse(String(call[0])));
    expect(commands.at(-1)).toMatchObject({ type: "sync", state: "speaking" });
    // renderer 以 sequence 擋重複投遞，倒退或重複會被它整個忽略。
    // ⚠️ 只看 `sync`：`look`／`tap`／`greet` 依設計不吃序號（它們不是狀態，與 `sync`
    // 共用序號會讓兩者互相擋掉，見 `shared/ottoBridge.ts`）。
    const sequences = commands
      .filter((command) => command.type === "sync")
      .map((command) => command.sequence);
    expect(sequences.length).toBeGreaterThan(1);
    expect([...sequences]).toEqual([...sequences].sort((a, b) => a - b));
  });

  it("ready 之前不送——iframe 還沒接手，送了也是丟掉", () => {
    const { rerender } = render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    rerender(<BearStage state="thinking" />);
    expect(post).not.toHaveBeenCalled();
  });

  it("iframe 不給 allow-same-origin：renderer 出事也碰不到頁面的 storage", () => {
    render(<BearStage state="idle" />);
    const frame = document.querySelector("iframe")!;
    expect(frame.getAttribute("sandbox")).toBe("allow-scripts");
  });
});

/** 走完「ready → 換成這組 props」，回傳 renderer 收到的最後一個指令。 */
function lastCommandAfter(props: Parameters<typeof BearStage>[0]) {
  const { rerender } = render(<BearStage state="idle" />);
  const post = vi.spyOn(iframeWindow(), "postMessage");
  emitReady(iframeWindow());
  rerender(<BearStage {...props} />);
  const commands = post.mock.calls.map((call) => JSON.parse(String(call[0])));
  return commands.at(-1);
}

describe("說話對嘴的原料", () => {
  // ⚠️ 這裡驗的是「呈現層有沒有把原料交出去」，不是 renderer 內部怎麼對嘴——後者
  // 由 `app/scripts/test-otto-runtime.mjs` 在真的跑起來的 DOM 上驗，兩邊不重複。
  // 這一層壞掉的症狀是**沒有編譯錯誤、沒有測試紅**，只是阿白說話時嘴不會動。

  it("speaking 時把這一則的字與時長送給 renderer", () => {
    const command = lastCommandAfter({
      state: "speaking",
      speechCue: { key: "t1:reply:1", text: "今天天氣很好", durationMs: 1200 },
    });
    expect(command).toMatchObject({
      state: "speaking",
      text: "今天天氣很好",
      durationMs: 1200,
    });
  });

  it("同一句重播也要送出新指令：key 不同，renderer 才會重新對嘴", () => {
    const { rerender } = render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    const spoken = { text: "該吃藥了喔", durationMs: 900 };
    rerender(<BearStage state="speaking" speechCue={{ key: "t1:reply:1", ...spoken }} />);
    rerender(<BearStage state="speaking" speechCue={{ key: "t1:reply:2", ...spoken }} />);

    const commands = post.mock.calls.map((call) => JSON.parse(String(call[0])));
    const speaking = commands.filter((command) => command.state === "speaking");
    expect(speaking).toHaveLength(2);
    // renderer 以 sequence 擋重複投遞（見 kinsun-bridge.js）：第二次沒有更大的
    // sequence 就會被整個忽略，同一句重播時嘴巴不會再動。
    expect(speaking[1].sequence).toBeGreaterThan(speaking[0].sequence);
  });

  it("非 speaking 態不帶字：協定只在說話時需要對嘴原料", () => {
    const command = lastCommandAfter({
      state: "thinking",
      speechCue: { key: "t1:reply:1", text: "今天天氣很好", durationMs: 1200 },
    });
    expect(command).toMatchObject({ state: "thinking" });
    expect(command).not.toHaveProperty("text");
  });
});

describe("進畫面打招呼", () => {
  function greetCommands(post: { mock: { calls: unknown[][] } }) {
    return post.mock.calls
      .map((call) => JSON.parse(String(call[0])) as Record<string, unknown>)
      .filter((command) => command.type === "greet");
  }

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renderer 一就緒就揮手打招呼", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    expect(greetCommands(post)).toHaveLength(1);
  });

  it("打招呼排在狀態指令後面——先知道自己該是什麼樣子，再演", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    const types = post.mock.calls.map((call) => JSON.parse(String(call[0])).type);
    expect(types).toEqual(["sync", "greet"]);
  });

  it("只打一次招呼——之後的狀態變化不會再觸發", () => {
    const { rerender } = render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    rerender(<BearStage state="listening" />);
    rerender(<BearStage state="idle" />);
    expect(greetCommands(post)).toHaveLength(1);
  });

  it("就緒時長輩已經在講話了就不打招呼——他正在等答案", () => {
    render(<BearStage state="thinking" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    expect(greetCommands(post)).toHaveLength(0);
  });

  it("減少動態效果時不打招呼", () => {
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    expect(greetCommands(post)).toHaveLength(0);
  });
});

describe("視線追蹤", () => {
  // ⚠️ 這一組驗的是「阿白會看著你」的**外層接線**：座標換算、節流、回正與
  // reduced-motion 尊重。renderer 收到 look 之後怎麼轉頭轉眼珠是它自己的事。

  /** 把舞台釘在視窗正中央（jsdom 的 getBoundingClientRect 一律回 0）。 */
  function centerStageAt(x: number, y: number) {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      left: x - 104.5,
      top: y - 150,
      width: 209,
      height: 300,
      right: x + 104.5,
      bottom: y + 150,
      x: x - 104.5,
      y: y - 150,
      toJSON: () => ({}),
    });
  }

  /** rAF 節流在測試裡同步跑完，才不必為了一則訊息等真的動畫幀。 */
  function runFramesSynchronously() {
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      cb(0);
      return 1;
    });
  }

  function movePointer(clientX: number, clientY: number, pointerType = "mouse") {
    const event = new Event("pointermove") as Event & Record<string, unknown>;
    event.clientX = clientX;
    event.clientY = clientY;
    event.pointerType = pointerType;
    window.dispatchEvent(event);
  }

  function lookCommands(post: { mock: { calls: unknown[][] } }) {
    return post.mock.calls
      .map((call) => JSON.parse(String(call[0])) as Record<string, unknown>)
      .filter((command) => command.type === "look");
  }

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    centerStageAt(512, 350); // 視窗 1024×768 的正中央
    runFramesSynchronously();
  });

  it("指標移動時把方向送給 renderer，換算成 -1..1", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    // 視窗半寬 512：往右 256 就是右半邊的一半。
    movePointer(512 + 256, 350);
    expect(lookCommands(post).at(-1)).toMatchObject({ type: "look", x: 0.5, y: 0 });
  });

  it("指標超出視窗邊界時夾在 ±1，不會讓阿白轉到脖子後面", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    movePointer(99_999, -99_999);
    expect(lookCommands(post).at(-1)).toMatchObject({ x: 1, y: -1 });
  });

  it("手指離開畫面後視線回正", () => {
    // ⚠️ 只有觸控要在放開時回正：滑鼠放開按鍵不代表人走了，視線該留在原處。
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    movePointer(700, 400, "touch");
    const event = new Event("pointerup") as Event & Record<string, unknown>;
    event.pointerType = "touch";
    window.dispatchEvent(event);
    expect(lookCommands(post).at(-1)).toMatchObject({ x: null, y: null });
  });

  it("滑鼠放開按鍵不算離開，視線留在原處", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    movePointer(512 + 256, 350, "mouse");
    const event = new Event("pointerup") as Event & Record<string, unknown>;
    event.pointerType = "mouse";
    window.dispatchEvent(event);
    expect(lookCommands(post).at(-1)).toMatchObject({ x: 0.5 });
  });

  it("滑鼠離開整個視窗時視線回正", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    movePointer(700, 400);
    document.dispatchEvent(new Event("mouseleave"));
    expect(lookCommands(post).at(-1)).toMatchObject({ x: null, y: null });
  });

  it("同一幀內移動很多次只送一則——指標事件的頻率遠高於畫面更新", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    // 這一條刻意讓 rAF **不要**同步跑完，才觀察得到「多次移動只排一次」。
    const scheduled: FrameRequestCallback[] = [];
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb) => {
      scheduled.push(cb);
      return 1;
    });
    movePointer(600, 350);
    movePointer(650, 350);
    movePointer(700, 350);
    expect(lookCommands(post)).toHaveLength(0);
    // 三次移動只排了一顆 rAF——這正是節流本身。
    expect(scheduled).toHaveLength(1);
    scheduled[0](0);
    const sent = lookCommands(post);
    expect(sent).toHaveLength(1);
    // 送出去的是**最後**那一個位置，不是第一個——中途的位置已經過期了。
    expect(sent[0].x).toBeCloseTo((700 - 512) / 512, 5);
  });

  it("使用者要求減少動態效果時完全不追蹤", () => {
    // 前庭功能障礙的使用者會因為跟著自己動的畫面而暈眩。renderer 那側也讀同一個
    // 系統設定關掉動畫，這裡是不要連訊息都送過去。
    // jsdom 沒有 `matchMedia`，所以 `prefersReducedMotion()` 平時一律回 false
    //（其餘測試因此走的是「要動」那條路）。
    vi.stubGlobal("matchMedia", () => ({ matches: true }));
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    movePointer(700, 400);
    expect(lookCommands(post)).toHaveLength(0);
  });

  it("renderer 還沒 ready 之前不送視線", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    movePointer(700, 400);
    expect(lookCommands(post)).toHaveLength(0);
  });
});

describe("待機可點道具", () => {
  // ⚠️ 道具的按鈕畫在**外層**而不是 renderer 裡：iframe 是 `pointer-events: none`
  // 且不給 `allow-same-origin`，畫在裡面點不到；而可以按的東西必須進得了輔助科技的
  // 樹，整個 iframe 卻是 aria-hidden 的裝飾層。

  const BUBBLE = {
    key: "bubble",
    icon: "🫧",
    label: "戳破泡泡",
    zh: "吹泡泡",
    x: 68,
    y: 26,
  };

  /** 模擬 renderer 說「現在浮出這個道具」（`null`＝收起來）。 */
  function emitIdleProp(source: Window | null, detail: unknown) {
    act(() => {
      window.dispatchEvent(
        new MessageEvent("message", {
          data: JSON.stringify({ version: 1, type: "idle-prop", detail }),
          source: source as MessageEventSource | null,
        }),
      );
    });
  }

  it("renderer 說有道具時畫出一顆可以按的鈕，位置用它給的舞台百分比", () => {
    render(<BearStage state="idle" />);
    emitReady(iframeWindow());
    emitIdleProp(iframeWindow(), BUBBLE);

    const prop = screen.getByTestId("bear-idle-prop");
    expect(prop).toHaveTextContent("🫧");
    expect(prop.style.left).toBe("68%");
    expect(prop.style.top).toBe("26%");
  });

  it("道具講得出自己是什麼、按下去會發生什麼", () => {
    // emoji 對讀螢幕軟體幾乎沒有資訊量（這條規則本畫面的表情符號早就踩過一次）。
    render(<BearStage state="idle" />);
    emitReady(iframeWindow());
    emitIdleProp(iframeWindow(), BUBBLE);
    expect(screen.getByRole("button", { name: "吹泡泡：戳破泡泡" })).toBeInTheDocument();
  });

  it("按下去把 tap 送給 renderer", () => {
    render(<BearStage state="idle" />);
    const post = vi.spyOn(iframeWindow(), "postMessage");
    emitReady(iframeWindow());
    emitIdleProp(iframeWindow(), BUBBLE);
    act(() => {
      screen.getByTestId("bear-idle-prop").click();
    });
    const commands = post.mock.calls.map((call) => JSON.parse(String(call[0])));
    expect(commands.at(-1)).toEqual({ version: 1, type: "tap" });
  });

  it("按過就收起來——renderer 那側一次待機也只認第一下", () => {
    render(<BearStage state="idle" />);
    emitReady(iframeWindow());
    emitIdleProp(iframeWindow(), BUBBLE);
    act(() => {
      screen.getByTestId("bear-idle-prop").click();
    });
    expect(screen.queryByTestId("bear-idle-prop")).not.toBeInTheDocument();
  });

  it("這段待機結束時道具跟著收起來", () => {
    render(<BearStage state="idle" />);
    emitReady(iframeWindow());
    emitIdleProp(iframeWindow(), BUBBLE);
    expect(screen.getByTestId("bear-idle-prop")).toBeInTheDocument();
    emitIdleProp(iframeWindow(), null);
    expect(screen.queryByTestId("bear-idle-prop")).not.toBeInTheDocument();
  });

  it("阿白在聽、在想或在講話時不顯示道具", () => {
    // ⚠️ 長輩正要說話或正在聽答案時，畫面上不可以多一個會動的東西跟麥克風鍵搶手指。
    // renderer 那側待機被 suspend 時本來就會送收起來，但狀態切換與訊息抵達之間有
    // 空窗，這裡不賭那個順序。
    const { rerender } = render(<BearStage state="idle" />);
    emitReady(iframeWindow());
    emitIdleProp(iframeWindow(), BUBBLE);
    expect(screen.getByTestId("bear-idle-prop")).toBeInTheDocument();
    rerender(<BearStage state="listening" />);
    expect(screen.queryByTestId("bear-idle-prop")).not.toBeInTheDocument();
  });

  it("不是自己 iframe 送來的道具一律不理", () => {
    render(<BearStage state="idle" />);
    emitReady(iframeWindow());
    emitIdleProp(window, BUBBLE);
    expect(screen.queryByTestId("bear-idle-prop")).not.toBeInTheDocument();
  });

  it("欄位缺漏或座標不是數字的道具當作沒有，不讓 NaN% 流進畫面", () => {
    render(<BearStage state="idle" />);
    emitReady(iframeWindow());
    emitIdleProp(iframeWindow(), { ...BUBBLE, x: "很右邊" });
    expect(screen.queryByTestId("bear-idle-prop")).not.toBeInTheDocument();
    emitIdleProp(iframeWindow(), { icon: "🫧" });
    expect(screen.queryByTestId("bear-idle-prop")).not.toBeInTheDocument();
  });

  it("道具是舞台上唯一對輔助科技可見的東西——光暈與 renderer 仍是裝飾", () => {
    render(<BearStage state="idle" />);
    emitReady(iframeWindow());
    emitIdleProp(iframeWindow(), BUBBLE);
    expect(screen.getByTestId("bear-stage-glow")).toHaveAttribute("aria-hidden", "true");
    expect(document.querySelector("iframe")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByTestId("bear-idle-prop")).not.toHaveAttribute("aria-hidden");
  });
});

describe("情緒黑名單", () => {
  // ⚠️ CRITICAL（接手指示第 10 條）：阿白可以同理長輩的不舒服，但不能對長輩表現
  // 生氣、不耐、嫌惡、猜忌或驚慌。renderer 內的 `PET.sanitizeEmotion` 是執行期的
  // 真防線；這一層是**送出去之前**就先擋掉，與 App 端 `BearStage.tsx` 同形。

  it("黑名單情緒不會送到 renderer", () => {
    const command = lastCommandAfter({
      state: "speaking",
      emotion: "angry",
      speechCue: { key: "t1:reply:1", text: "你很煩", durationMs: 500 },
    });
    expect(command).toMatchObject({ state: "speaking", text: "你很煩" });
    expect(command).not.toHaveProperty("emotion");
  });

  it("允許的情緒照送——擋的是傷人的那幾種，不是全部", () => {
    const command = lastCommandAfter({
      state: "speaking",
      emotion: "grateful",
      speechCue: { key: "t1:reply:1", text: "謝謝您", durationMs: 500 },
    });
    expect(command).toMatchObject({ emotion: "grateful" });
  });

  it("sanitizeEmotion 對每一個黑名單情緒都回 null", () => {
    for (const emotion of BLOCKED_EMOTIONS) {
      expect(sanitizeEmotion(emotion)).toBeNull();
    }
    expect(sanitizeEmotion("calm")).toBe("calm");
    expect(sanitizeEmotion(null)).toBeNull();
  });

  it("這份黑名單與 renderer 的 BLOCKED_EMOTIONS 是同一份", () => {
    // ⚠️ 兩份清單漂掉**不會有任何症狀**，直到長輩罵阿白的那一刻。App 端由
    // `test-otto-runtime.mjs` 對 `theme.ts` 做同一件事；web 這一份原本沒有任何
    // 閘門守著，那正是「第三份會各自演化的清單」的起點。
    const block = rendererHtml.match(/BLOCKED_EMOTIONS = new Set\(\[([\s\S]*?)\]\)/);
    expect(block, "renderer 產物找不到 BLOCKED_EMOTIONS").not.toBeNull();
    const rendererBlocked = Array.from(block![1].matchAll(/"([a-z]+)"/g)).map((m) => m[1]);
    expect(rendererBlocked.length).toBeGreaterThan(0);
    expect([...BLOCKED_EMOTIONS].sort()).toEqual([...rendererBlocked].sort());
  });
});
