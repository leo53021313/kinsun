/** 雙欄舞台：兩欄都在、窄螢幕以頁籤切換。 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { StagePage } from "./StagePage";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

/**
 * 可控制的假 `matchMedia`。
 *
 * ⚠️ jsdom 沒有這個 API（實測 `typeof window.matchMedia` 是 `undefined`），所以
 * **沒有呼叫這支的測試都跑在「不是寬螢幕」的路徑上**——那正是頁籤模式的語意，
 * 既有測試因此完全不受影響。
 */
function stubMatchMedia(isWide: boolean) {
  const listeners = new Set<() => void>();
  const query = {
    matches: isWide,
    addEventListener: (_event: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_event: string, listener: () => void) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return {
    /** 模擬使用者把視窗拉寬／縮窄，或按 Ctrl+ 改變字級（`lg` 是 CSS px）。 */
    setWide(next: boolean) {
      query.matches = next;
      act(() => listeners.forEach((listener) => listener()));
    },
  };
}

/**
 * 同 `elder/bind.test.tsx` 的既有慣例：整支 `talk/qrScanner.ts` 換成假的，
 * 只留呼叫端傳入的 `onCode`／`onError` 存起來，測試自己決定何時觸發。這裡
 * 要驗證的是**切頁籤**這個 `StagePage` 層級的行為，所以在這個檔案獨立重建
 * 一份同款 mock（各測試檔自己顧自己的 mock，同本專案既有慣例），不是在
 * `elder/bind.test.tsx` 裡驗證得到的。
 */
const scannerState = vi.hoisted(() => ({ stop: vi.fn(), createCount: 0 }));
vi.mock("@/talk/qrScanner", () => ({
  createQrScanner: () => {
    scannerState.createCount += 1;
    return { stop: scannerState.stop };
  },
}));

beforeEach(() => {
  localStorage.clear();
  // ⚠️ 歸零放在 beforeEach 而非 afterEach：`@testing-library/react` 的自動 cleanup
  // 也是 afterEach，而它**晚於**本檔的 afterEach 執行——上一條測試卸載時
  // `BindScreen` 的 effect cleanup 會再呼叫一次 `scanner.stop()`，那一筆就會落在
  // 下一條測試的帳上（實測：寬螢幕那條因此看到一次不存在的 stop）。
  scannerState.stop.mockClear();
  scannerState.createCount = 0;
});
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("StagePage", () => {
  it("兩支手機同時在畫面上", () => {
    render(<StagePage />);
    expect(screen.getByRole("region", { name: "長輩的手機" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "家屬的手機" })).toBeInTheDocument();
  });

  it("長輩欄顯示真正的配對畫面，不是佔位元件（P3 Task 7 接上 ElderApp）", () => {
    render(<StagePage />);
    expect(screen.getByText("掃描家人給的方塊圖，或輸入號碼")).toBeInTheDocument();
  });

  it("窄螢幕的切換頁籤兩個都在", () => {
    render(<StagePage />);
    expect(screen.getByRole("tab", { name: "長輩端" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "家屬端" })).toBeInTheDocument();
  });

  it("預設選中長輩端", () => {
    render(<StagePage />);
    expect(screen.getByRole("tab", { name: "長輩端" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "家屬端" })).toHaveAttribute("aria-selected", "false");
  });

  it("點頁籤可以切換", async () => {
    render(<StagePage />);
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    expect(screen.getByRole("tab", { name: "家屬端" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "長輩端" })).toHaveAttribute("aria-selected", "false");
  });

  it("長輩欄正在掃 QR 時切到家屬端頁籤會關閉相機（審查發現的 Critical）", async () => {
    // ⚠️ 窄螢幕是頁籤擇一顯示，非活動欄只是被 CSS `hidden` 蓋住、元件仍掛著
    // ——`MediaStream` 軌道與 `display:none` 無關，不會因為看不見就自己關閉。
    // 若切頁籤不會讓長輩欄停止掃描，相機會一直開到分頁關閉為止。
    render(<StagePage />);
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    expect(scannerState.createCount).toBe(1);
    expect(scannerState.stop).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    expect(scannerState.stop).toHaveBeenCalled();
    // ⚠️ 只斷言 stop() 被呼叫還不夠——一個更隱蔽的半套修法是「切走時關掉舊的，
    // 但沒同時擋住『再建一顆新的』」，那樣 stop() 一樣會被呼叫到，相機卻立刻
    // 重新開啟，指示燈依然亮著。切走後 createCount 必須維持 1（沒有再建立
    // 任何新的 scanner），camera 才是真的關閉而非「關了又馬上開」。
    expect(scannerState.createCount).toBe(1);
  });

  it("切回長輩端頁籤時，掃描仍在進行中會自動恢復（不強迫重新按「掃描 QR 碼」）", async () => {
    render(<StagePage />);
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    scannerState.stop.mockClear();
    await userEvent.click(screen.getByRole("tab", { name: "長輩端" }));
    // 切回來後畫面仍是「把方塊圖對準框框」的掃描畫面，不是被強迫退回手動輸入。
    expect(screen.getByText("把家人給的方塊圖對準框框")).toBeInTheDocument();
    // 切回來要重新要求鏡頭（權限已授予，瀏覽器不會再跳一次對話框）才能真的
    // 恢復畫面，不是留著一個早就被關掉的舊串流。
    expect(scannerState.createCount).toBe(2);
  });
});

/**
 * ⚠️ **全分支審查抓到的 Important 2**：`elderVisible` 原本是 `pane === "elder"`，
 * 而頁籤是 `lg:hidden`。組員把視窗縮窄（或按 Ctrl+ 放大投影字級——Tailwind 的 `lg`
 * 是 1024 CSS px，縮放直接改變它）→ 點「家屬端」→ 再放大回去，兩欄又同時可見，但
 * `pane` 仍是 `"guardian"`。長輩欄看起來完全正常（`useTalk` 的 cleanup 把字幕重設回
 * 「按住下面的麥克風說話」、avatar 是 😊），麥克風卻永遠打不開，而 `lg` 以上頁籤是
 * `display:none`——畫面上不存在任何能把 `pane` 撥回來的 UI。而投影機上的那一欄，
 * 正是所有人在看的那一欄。
 *
 * 這裡以相機當觀察窗（`visible` 那條鏈上唯一在無頭環境測得到的效果，麥克風與長連線
 * 走的是同一個 prop）。
 */
describe("寬螢幕兩欄同時可見時的長輩欄", () => {
  it("點頁籤不可以把還開著的長輩欄關掉（兩欄都看得見，沒有「切走」這回事）", async () => {
    stubMatchMedia(true);
    render(<StagePage />);
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    expect(scannerState.createCount).toBe(1);

    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));

    expect(scannerState.stop).not.toHaveBeenCalled();
    expect(scannerState.createCount).toBe(1);
  });

  it("窄螢幕切到家屬端之後把螢幕變寬，長輩欄要活過來", async () => {
    const media = stubMatchMedia(false);
    render(<StagePage />);
    await userEvent.click(screen.getByRole("button", { name: "掃描 QR 碼" }));
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    // 窄螢幕的既有行為不變：切走就關掉相機。
    expect(scannerState.stop).toHaveBeenCalled();
    expect(scannerState.createCount).toBe(1);

    media.setWide(true);

    // 兩欄又同時看得見了：長輩欄必須跟著回來，否則它會停在一個看起來正常、
    // 實際上麥克風永遠打不開的狀態，而且沒有任何 UI 救得回來。
    expect(scannerState.createCount).toBe(2);
  });
});

/**
 * 跨欄連動的另一半（P4 Task 3）：家屬產生綁定碼後直接送到長輩欄，省去在同一個
 * 瀏覽器分頁裡「拿一欄的相機去掃另一欄螢幕上的 QR」這種不切實際的操作
 * （spec W-15 內測捷徑）。這裡驗證的正是「另一欄沒登入時怎樣」——長輩欄預設
 * 就停在未配對的配對畫面（`ElderApp` 沒有 session 時路由到 `bind`），這正是
 * 這條捷徑存在的目的：家屬按下去，長輩欄立刻收到碼。
 */
describe("跨欄連動：家屬把綁定碼送到長輩欄", () => {
  it("家屬新增長輩後按「送到長輩的手機」，長輩欄立刻收到綁定碼，窄螢幕並自動切回長輩端頁籤", async () => {
    localStorage.setItem(
      "kinsun_web_session_guardian",
      JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string, init?: RequestInit) => {
        if (String(path).includes("/elders") && init?.method === "POST") {
          return Promise.resolve({
            status: 201,
            json: async () =>
              envelope({ elder_id: "e9", name: "阿公", nickname: "", invite_code: "AB12CD" }),
          });
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    // 窄螢幕預設停在長輩端頁籤，先切到家屬端才拿得到「建立長輩檔案」表單。
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。");
    await userEvent.type(screen.getByLabelText("長輩稱呼"), "阿公");
    await userEvent.click(screen.getByRole("button", { name: "建立長輩檔案" }));
    await screen.findByText("AB12CD");

    await userEvent.click(screen.getByRole("button", { name: "送到長輩的手機" }));

    // 窄螢幕頁籤模式下另一欄不在畫面上，連動了家屬也看不到——自動切回長輩端
    // 頁籤，他才看得到「已經送過去了」的反應。
    expect(screen.getByRole("tab", { name: "長輩端" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "家屬端" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByLabelText("綁定碼")).toHaveValue("AB12CD");
    expect(screen.getByText("已從家屬手機收到號碼")).toBeInTheDocument();
  });

  it("寬螢幕兩欄同時可見時按下送出，長輩欄不需要切頁籤也能立刻看到碼", async () => {
    stubMatchMedia(true);
    localStorage.setItem(
      "kinsun_web_session_guardian",
      JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string, init?: RequestInit) => {
        if (String(path).includes("/elders") && init?.method === "POST") {
          return Promise.resolve({
            status: 201,
            json: async () =>
              envelope({ elder_id: "e9", name: "阿嬤", nickname: "", invite_code: "ZZ99YY" }),
          });
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    await screen.findByText("還沒有長輩檔案，先在上面建立一位吧。");
    await userEvent.type(screen.getByLabelText("長輩稱呼"), "阿嬤");
    await userEvent.click(screen.getByRole("button", { name: "建立長輩檔案" }));
    await screen.findByText("ZZ99YY");

    await userEvent.click(screen.getByRole("button", { name: "送到長輩的手機" }));

    expect(screen.getByLabelText("綁定碼")).toHaveValue("ZZ99YY");
    expect(screen.getByText("已從家屬手機收到號碼")).toBeInTheDocument();
  });
});

/**
 * P4 Task 4：兩欄接上通知。
 *
 * ⚠️ **brief 原始版本的測試已修正**：brief 給的第一條測試設定已讀水位不是 0、
 * 只餵一批固定資料（`mockImplementation` 每次都回同一批），期待掛載後立刻看到
 * 橫幅。這與 `notify/useNotificationFeed.ts` 刻意規定的「第一次載入不補播歷史，
 * 且與已讀水位無關，一律以自己掛載後第一輪輪詢為準」互相矛盾（見該檔「brief
 * 缺陷 2」）：第一輪輪詢只會把這批資料當成基準記下來，之後同一批資料的
 * `created_at` 不會再大於這個基準，橫幅永遠不會出現（實測驗證：套用 brief 原始
 * 寫法跑到逾時）。改為兩輪：第一輪回舊資料建立基準，第二輪追加一則更新的，
 * 觸發方式沿用 `useNotificationFeed.test.ts` 自己的既有手法——分派
 * `visibilitychange` 事件讓 hook 立刻重拉一次，不必等 2 秒的真實輪詢間隔。
 */
describe("通知橫幅", () => {
  it("長輩端有新提醒時在左邊的手機外框上滑出橫幅", async () => {
    localStorage.setItem(
      "kinsun_web_session_elder",
      JSON.stringify({ role: "elder", token: "tok", display_name: "王阿嬤" }),
    );
    let pollCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string) => {
        if (String(path).includes("elder-notifications")) {
          pollCount += 1;
          const data =
            pollCount === 1
              ? [{ content: "舊提醒", created_at: 1754000050 }]
              : [
                  { content: "舊提醒", created_at: 1754000050 },
                  { content: "提醒您：降血壓藥", created_at: 1754000100 },
                ];
          return Promise.resolve({ status: 200, json: async () => envelope(data) });
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    // 第一輪輪詢（建立基準，不播）跑完再觸發第二輪。
    await waitFor(() => expect(pollCount).toBe(1));
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    const content = await screen.findByText("提醒您：降血壓藥");
    expect(content).toBeInTheDocument();
    // ⚠️ 審查發現的 Important 4：`size="big"` 若被拿掉（例如日後有人把兩欄的
    // `notificationSlot` 抽成共用元件時漏傳），長輩欄橫幅會退回 12px／14px、
    // 跌破 22px 下限——而這句「提醒您：降血壓藥」恰好是長輩唯一該讀的話。
    // 已實測：拿掉 `size="big"` 之後 `StagePage.test.tsx`＋`NotificationBanner.test.tsx`
    // 兩支測試合計 35/35 全過，沒有任何一條會發現。
    expect(content.className).toContain("text-elder-min");
  });

  /**
   * ⚠️ brief 原始版本只斷言「按鈕存在、點了不會炸」，沒有斷言點下去真的
   * 改變了什麼——這正是這份 spec 反覆抓到的「恰好通過的假測試」形狀（實測：
   * 把 `onClick` 換成空函式，brief 原始寫法仍然全綠）。改用 `PhoneFrame` 的
   * `dynamic-island`（只有 iOS 樣式才畫）當觀察窗，同時驗證「兩欄同步」這件
   * 事本身——brief 修正前兩欄是各自寫死 `ios`／`android`，這裡若沒有真的改成
   * 共用同一個 `os` state，會看到 0 或 1 個瀏海，不會是兩個一起出現／消失。
   */
  it("可以切換通知的作業系統風格，且兩欄同步套用同一種樣式", async () => {
    render(<StagePage />);
    // jsdom 的 navigator.userAgent 不含 iPhone／iPad／Macintosh，預設會判成
    // Android 風（見 `notify/osStyle.ts::detectOs`），兩欄一開始都不畫瀏海。
    expect(screen.queryAllByTestId("dynamic-island")).toHaveLength(0);

    const toggle = screen.getByRole("button", { name: /通知樣式/ });
    await userEvent.click(toggle);
    expect(screen.queryAllByTestId("dynamic-island")).toHaveLength(2);

    await userEvent.click(toggle);
    expect(screen.queryAllByTestId("dynamic-island")).toHaveLength(0);
  });
});

/**
 * ⚠️ **這條線一定要有測試守**（見任務交辦）：這是「非活動欄的長生命週期資源
 * 沒有隨可見性收掉」這一類坑第五次發生的地方，前四次分別是麥克風、相機、
 * 頁籤、播放器解鎖，全部是「程式碼寫對了、但沒有任何測試會在它被拿掉時
 * 變紅」。這裡刻意用網路請求次數當觀察窗——若 `visible={guardianVisible}`／
 * `visible={elderVisible}` 被拿掉（等於恆為預設值 `true`），下面兩條測試都會
 * 因為非活動欄照樣打請求而變紅（已實測，見任務報告的變異驗證段落）。
 */
describe("通知輪詢的可見性接線（elderVisible／guardianVisible／visible）", () => {
  it("窄螢幕預設在長輩端頁籤時，家屬欄的通知輪詢不會打；切過去後才開始打", async () => {
    localStorage.setItem(
      "kinsun_web_session_guardian",
      JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
    );
    const notifyFetch = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string) => {
        if (String(path).includes("/api/v1/notifications")) {
          notifyFetch();
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    await act(async () => {}); // 讓掛載時可能觸發的效果跑完
    expect(notifyFetch).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    await waitFor(() => expect(notifyFetch).toHaveBeenCalled());
  });

  it("切到家屬端頁籤後，長輩欄的通知輪詢跟著暫停", async () => {
    localStorage.setItem(
      "kinsun_web_session_elder",
      JSON.stringify({ role: "elder", token: "tok", display_name: "王阿嬤" }),
    );
    let elderCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string) => {
        if (String(path).includes("elder-notifications")) {
          elderCalls += 1;
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    await waitFor(() => expect(elderCalls).toBe(1)); // 掛載時的第一輪

    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    elderCalls = 0;
    // 若沒有暫停，這個事件會讓長輩欄立刻再打一次（同 `useNotificationFeed`
    // 自己「切回前景立刻補一次」測試的手法）。
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(elderCalls).toBe(0);
  });
});

describe("通知輪詢的 401 出口接線（onTokenRevoked）", () => {
  it("長輩欄的通知輪詢收到 401（token 被撤銷）時，立刻退回配對畫面且顯示說明", async () => {
    localStorage.setItem(
      "kinsun_web_session_elder",
      JSON.stringify({ role: "elder", token: "tok", display_name: "王阿嬤" }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string) => {
        if (String(path).includes("elder-notifications")) {
          return Promise.resolve({
            status: 401,
            json: async () => ({
              success: false,
              data: null,
              error: { code: "invalid_token", message: "請重新配對" },
              meta: null,
            }),
          });
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    // 沒有這條接線的話，這支輪詢會每 2 秒收到一次註定失敗的 401、完全靜默
    // 丟棄，長輩欄會停在對講機畫面，不會回到配對畫面。
    expect(await screen.findByText("掃描家人給的方塊圖，或輸入號碼")).toBeInTheDocument();
    // ⚠️ 審查發現的 Important 1：只回到配對畫面還不夠——若輪詢直接呼叫
    // `signOut()`（繞過 `ElderApp` 的 `loseSession`），會搶在 `useTalk` 既有的
    // 401 判定前面把人靜默登出，配對畫面上不會有任何說明。這句話必須出現。
    expect(screen.getByText("家人幫您重新設定了，請再掃一次他給的方塊圖，或輸入新的號碼。")).toBeInTheDocument();
  });

  /**
   * ⚠️ **審查發現的 Important 3**：`elderFeed`／`guardianFeed` 的
   * `onTokenRevoked` 是幾乎逐字相同的兩段複製貼上，日後任何人動這裡接錯（例如
   * 把 `guardian.signOut` 誤植為 `elder.signOut`），後果是「家屬 token 過期時
   * 被登出的是長輩欄，家屬欄反而留在原畫面每 2 秒吃一次註定失敗的 401」——
   * 且**沒有任何既有測試會在它被接錯時變紅**。上面那條長輩欄測試不會發現這個
   * 錯誤（那次測試裡家屬欄根本沒有 session，`guardianFeed` 的 token 是空字串，
   * 不會打任何請求），故獨立補一條家屬欄專屬的測試。
   */
  it("家屬欄的通知輪詢收到 401 時，退回登入畫面（不是長輩欄被登出）", async () => {
    localStorage.setItem(
      "kinsun_web_session_guardian",
      JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string) => {
        if (String(path).includes("/api/v1/notifications")) {
          return Promise.resolve({
            status: 401,
            json: async () => ({
              success: false,
              data: null,
              error: { code: "invalid_token", message: "請重新登入" },
              meta: null,
            }),
          });
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    // 窄螢幕預設在長輩端頁籤，家屬欄的通知輪詢要先切過去才會開始打
    // （`guardianVisible` 接線，見上面「通知輪詢的可見性接線」describe）。
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    expect(await screen.findByRole("heading", { name: "家屬登入" })).toBeInTheDocument();
  });
});

describe("未讀數接上真正的輪詢結果（不再寫死 0／恆無徽章）", () => {
  it("長輩欄的鈴鐺未讀數接上 elderFeed.unread", async () => {
    localStorage.setItem(
      "kinsun_web_session_elder",
      JSON.stringify({ role: "elder", token: "tok", display_name: "王阿嬤" }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string) => {
        if (String(path).includes("elder-notifications")) {
          return Promise.resolve({
            status: 200,
            json: async () => envelope([{ content: "吃藥囉", created_at: 1754000100 }]),
          });
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    expect(await screen.findByRole("button", { name: "看金孫的提醒，1 則新的" })).toBeInTheDocument();
  });

  it("家屬端首頁的通知鈕接上 guardianFeed.unread", async () => {
    localStorage.setItem(
      "kinsun_web_session_guardian",
      JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((path: string) => {
        if (String(path).includes("/api/v1/notifications")) {
          return Promise.resolve({
            status: 200,
            json: async () => envelope([{ content: "王阿嬤說胸口悶", created_at: 1754000100 }]),
          });
        }
        return Promise.resolve({ status: 200, json: async () => envelope([]) });
      }),
    );
    render(<StagePage />);
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    expect(await screen.findByRole("button", { name: "通知，1 則新的" })).toBeInTheDocument();
  });
});
