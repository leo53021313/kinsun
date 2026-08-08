/**
 * 家屬端框內導覽與登入狀態守衛。
 *
 * ⚠️ 這個檔補的是 P2 七個工項之間的接縫——每個工項各自都測過自己那一頁，但
 * 「從 A 頁真的走到 B 頁」與「登入狀態消失時畫面跟著退回去」沒有任何人測過。
 * 全分支審查逐條推過變異證實：把 `GuardianApp` 的 401 守衛整段 effect 刪掉、
 * 把「管理行程」的 `onClick` 換成空函式、把登出鈕整顆拿掉，先前 167 條測試
 * 依然全綠（每一條變異的實測輸出見 whole-branch-fix-report.md）。
 *
 * 與 `auth.test.tsx` 的分工：那邊是註冊／登入這條旅程本身，這邊是路由與 session
 * 生命週期。
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { GuardianApp } from "./GuardianApp";

const SESSION_KEY = "kinsun_web_session_guardian";

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
}

function failure(code: string, message: string) {
  return { success: false, data: null, error: { code, message }, meta: null };
}

/** 依請求路徑回不同的資料。key 順序由具體到籠統——`path.includes(key)` 取第一個
 *  符合的，而 `/elders/e1/schedules` 這種子資源路徑本身就含有 "elders"。 */
function mockByPath(map: Record<string, unknown>) {
  const spy = vi.fn().mockImplementation((path: string) => {
    const key = Object.keys(map).find((k) => String(path).includes(k));
    return Promise.resolve({ status: 200, json: async () => envelope(key ? map[key] : null) });
  });
  vi.stubGlobal("fetch", spy);
  return spy;
}

function renderSignedIn() {
  localStorage.setItem(
    SESSION_KEY,
    JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
  );
  return render(
    <GuardianSession.Provider>
      <GuardianApp />
    </GuardianSession.Provider>,
  );
}

const ELDERS = [{ elder_id: "e1", name: "王阿嬤", nickname: "" }];

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("登入狀態守衛", () => {
  // ⚠️ 這是 docs/dev/07 §7 列在 `guardian/` **第一條**的關鍵不變量，先前一條測試
  // 都沒有。token 在別台裝置被撤銷後若還停在原畫面，上面會掛著最後一次成功載入
  // 的資料，看起來像還連得上——而家屬會據此以為長輩一切正常。
  it("後端回 401 時清掉登入狀態並退回登入畫面，不停在有資料的舊畫面", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 401,
        json: async () => failure("unauthorized", "請重新登入"),
      }),
    );
    renderSignedIn();
    // ⚠️ timeout 拉到 5 秒不是為了讓它過：`findBy*` 的語意是「等到出現為止，逾時
    // 才失敗」，上限只決定多晚判定沒出現，不改變這條在驗什麼。真的不會退回登入
    // 畫面的話，等 5 秒照樣紅。
    //
    // 為什麼要拉：這條要走完「401 → 清 session → 重繪回登入畫面」跨數次 re-render
    // 的轉場，而 43 支測試檔平行跑時單機負載高，預設 1 秒不夠。症狀是全庫跑穩定
    // 紅、單獨跑穩定綠，2026-08-09 以 `vitest run --no-file-parallelism` 實測確認
    // ——關掉平行後全過，是等待上限問題不是產品時序缺陷。
    //
    // 刻意只調這一條、不在 test-setup 調全域：本檔用真時鐘，但 `elder/useTalk.test.ts`
    // 用 `vi.useFakeTimers`，而 `waitFor` 在假時鐘下會自己推進時間——全域拉高等於
    // 允許它多推進 4 秒假時間，可能觸發該檔正在驗的那些保險計時器（實測改全域後
    // 「打斷長回覆」那條就開始間歇性紅）。
    expect(
      await screen.findByRole("heading", { name: "家屬登入" }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "我的長輩" })).not.toBeInTheDocument();
    // 本機那份 session 也要真的被清掉，否則重新整理又會回到「已登入」。
    expect(localStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it("按登出會撤銷這個 token 並回到登入畫面", async () => {
    const spy = mockByPath({ elders: [] });
    renderSignedIn();
    await screen.findByRole("heading", { name: "我的長輩" });
    await userEvent.click(screen.getByRole("button", { name: "登出" }));

    expect(await screen.findByRole("heading", { name: "家屬登入" })).toBeInTheDocument();
    expect(localStorage.getItem(SESSION_KEY)).toBeNull();
    // 光是本機清掉不夠：token 沒撤銷的話它在伺服器上仍然有效（✅ D-25）。
    await waitFor(() =>
      expect(
        spy.mock.calls.some(
          ([path, init]) =>
            String(path) === "/api/v1/sessions" &&
            (init as RequestInit | undefined)?.method === "DELETE",
        ),
      ).toBe(true),
    );
  });

  it("登出後端失敗仍然要讓人登出，不可把他關在裡面", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((_path: string, init?: RequestInit) =>
        init?.method === "DELETE"
          ? Promise.reject(new TypeError("Failed to fetch"))
          : Promise.resolve({ status: 200, json: async () => envelope([]) }),
      ),
    );
    renderSignedIn();
    await screen.findByRole("heading", { name: "我的長輩" });
    await userEvent.click(screen.getByRole("button", { name: "登出" }));
    expect(await screen.findByRole("heading", { name: "家屬登入" })).toBeInTheDocument();
  });
});

describe("框內導覽", () => {
  it("我的長輩 → 長輩詳情 → 行程管理，一路真的走得到", async () => {
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [],
      elders: ELDERS,
    });
    renderSignedIn();

    await userEvent.click(await screen.findByRole("button", { name: /王阿嬤/ }));
    expect(await screen.findByRole("heading", { name: "王阿嬤" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "管理行程" }));
    // 標題同時釘住「有走到排程頁」與「路由把 elderName 一起帶過來了」。
    expect(
      await screen.findByRole("heading", { name: "王阿嬤的行程管理" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "新增提醒" })).toBeInTheDocument();
  });

  it("從行程管理按兩次返回回得到我的長輩", async () => {
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [],
      elders: ELDERS,
    });
    renderSignedIn();
    await userEvent.click(await screen.findByRole("button", { name: /王阿嬤/ }));
    await userEvent.click(await screen.findByRole("button", { name: "管理行程" }));
    await screen.findByRole("heading", { name: "王阿嬤的行程管理" });

    await userEvent.click(screen.getByRole("button", { name: "返回" }));
    expect(await screen.findByRole("heading", { name: "王阿嬤" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "返回" }));
    expect(await screen.findByRole("heading", { name: "我的長輩" })).toBeInTheDocument();
  });

  it("通知改成分頁：切過去看得到內容，切回首頁不用「返回」", async () => {
    // W5b 起通知不再是 push 出來的深層頁，而是五項導覽之一。分頁之間是平行的，
    // 用底部導覽列橫向切換——這裡刻意斷言**沒有**返回鍵：留著它會讓人以為分頁
    // 有先後順序。
    mockByPath({
      notifications: [{ content: "王阿嬤說胸口悶", created_at: 1754000000 }],
      elders: [],
    });
    renderSignedIn();
    await userEvent.click(await screen.findByRole("tab", { name: /通知/ }));
    expect(await screen.findByText("王阿嬤說胸口悶")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "返回" })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /首頁/ }));
    expect(await screen.findByRole("heading", { name: "我的長輩" })).toBeInTheDocument();
  });
});

describe("五項導覽（W5b）", () => {
  it("四個分頁都有文字標籤，中央是動作不是分頁", async () => {
    // 設計稿明文「每個圖示都有文字標籤」。只有圖示的導覽對不熟 App 的家屬
    // 等於一排猜謎。中央那顆刻意**不是** tab：它導去別的地方，標成 tab 會讓
    // 讀螢幕的人以為按下去會停在那一頁。
    mockByPath({ elders: ELDERS });
    renderSignedIn();
    await screen.findByRole("heading", { name: "我的長輩" });

    const tabs = screen.getAllByRole("tab");
    expect(tabs.map((tab) => tab.textContent)).toEqual([
      expect.stringContaining("首頁"),
      expect.stringContaining("報告"),
      expect.stringContaining("通知"),
      expect.stringContaining("王阿嬤"),
    ]);
    expect(screen.getByTestId("guardian-add-action")).toHaveAccessibleName("新增用藥或回診提醒");
    expect(screen.getByTestId("guardian-add-action")).not.toHaveAttribute("role", "tab");
  });

  it("「我的」那一項顯示長輩的稱呼，不是寫死的字", async () => {
    mockByPath({ elders: [{ elder_id: "e1", name: "王大明", nickname: "阿公" }] });
    renderSignedIn();
    expect(await screen.findByRole("tab", { name: /阿公/ })).toBeInTheDocument();
  });

  it("目前在哪一頁用 aria-selected 揭露", async () => {
    mockByPath({ elders: ELDERS, notifications: [] });
    renderSignedIn();
    const home = await screen.findByRole("tab", { name: /首頁/ });
    expect(home).toHaveAttribute("aria-selected", "true");

    await userEvent.click(screen.getByRole("tab", { name: /報告/ }));
    expect(screen.getByRole("tab", { name: /報告/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /首頁/ })).toHaveAttribute("aria-selected", "false");
  });

  it("未讀數掛在通知分頁上", async () => {
    mockByPath({ elders: ELDERS });
    localStorage.setItem(
      SESSION_KEY,
      JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
    );
    render(
      <GuardianSession.Provider>
        <GuardianApp unread={3} />
      </GuardianSession.Provider>,
    );
    const bell = await screen.findByRole("tab", { name: /通知/ });
    expect(bell).toHaveTextContent("3");
  });

  it("進長輩詳情時導覽列消失，返回後回到原本那個分頁", async () => {
    // 深層頁不是分頁的同級選項，留著導覽列會讓人以為隨時可以橫向跳走。
    // 「返回後回到原本那個分頁」是 App 那批實機驗收特別點名的一條。
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [],
      elders: ELDERS,
    });
    renderSignedIn();
    await userEvent.click(await screen.findByRole("tab", { name: /報告/ }));
    await userEvent.click(await screen.findByRole("button", { name: "健康報告（近 30 天）" }));

    expect(screen.queryByTestId("guardian-tab-bar")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "返回" }));

    expect(await screen.findByTestId("guardian-tab-bar")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /報告/ })).toHaveAttribute("aria-selected", "true");
  });

  it("未登入時看不到導覽列", async () => {
    mockByPath({});
    render(
      <GuardianSession.Provider>
        <GuardianApp />
      </GuardianSession.Provider>,
    );
    expect(await screen.findByRole("heading", { name: "家屬登入" })).toBeInTheDocument();
    expect(screen.queryByTestId("guardian-tab-bar")).not.toBeInTheDocument();
  });
});

describe("中央新增鍵（W5b）", () => {
  it("有長輩時進行程管理頁——那裡才有新增區塊", async () => {
    mockByPath({
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [],
      elders: ELDERS,
    });
    renderSignedIn();
    await screen.findByRole("heading", { name: "我的長輩" });

    await userEvent.click(screen.getByTestId("guardian-add-action"));
    expect(await screen.findByRole("heading", { name: "王阿嬤的行程管理" })).toBeInTheDocument();
    expect(screen.queryByTestId("guardian-tab-bar")).not.toBeInTheDocument();
  });

  it("按下當刻重打一次 API，不讀快取", async () => {
    // ⚠️ 家屬剛在首頁建完第一位長輩，快取可能還是空的——讀快取會把他丟回首頁
    // 說「還沒有長輩」。這條守的就是那個時刻。
    const spy = mockByPath({ elders: ELDERS });
    renderSignedIn();
    await screen.findByRole("heading", { name: "我的長輩" });
    const before = spy.mock.calls.filter(([path]) => String(path).includes("elders")).length;

    await userEvent.click(screen.getByTestId("guardian-add-action"));
    await waitFor(() =>
      expect(
        spy.mock.calls.filter(([path]) => String(path).includes("elders")).length,
      ).toBeGreaterThan(before),
    );
  });

  it("還沒有長輩時帶回首頁並說明原因，不是按了沒反應", async () => {
    mockByPath({ elders: [] });
    renderSignedIn();
    await screen.findByRole("heading", { name: "我的長輩" });
    await userEvent.click(screen.getByRole("tab", { name: /報告/ }));

    await userEvent.click(screen.getByTestId("guardian-add-action"));
    expect(await screen.findByRole("heading", { name: "我的長輩" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("還沒有長輩檔案");
  });

  it("讀不到長輩時說出原因，不靜默失敗", async () => {
    // 按了沒反應會讓家屬一直按。
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 500,
        json: async () => failure("server_error", "伺服器忙碌中"),
      }),
    );
    renderSignedIn();
    await userEvent.click(await screen.findByTestId("guardian-add-action"));
    // 畫面上會有兩個 alert，兩個都是真的：首頁自己讀不到長輩清單、以及中央鍵這
    // 一次的失敗。這裡只驗中央鍵那一句真的說出了原因。
    expect(await screen.findByText("伺服器忙碌中")).toBeInTheDocument();
  });

  it("切換分頁會把上一次的錯誤收掉", async () => {
    mockByPath({ elders: [] });
    renderSignedIn();
    await screen.findByRole("heading", { name: "我的長輩" });
    await userEvent.click(screen.getByTestId("guardian-add-action"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /報告/ }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
