/** 家屬註冊與登入。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderToString } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GuardianSession } from "@/session/contexts";

import { GuardianApp } from "./GuardianApp";

function renderApp() {
  return render(
    <GuardianSession.Provider>
      <GuardianApp />
    </GuardianSession.Provider>,
  );
}

/**
 * 每一次 fetch 都回同一個值——只適合「這個測試只會打一次網路」的情境。
 *
 * ⚠️ 舊名 `mockOnce` 是錯的：它其實用 `mockResolvedValue`（不是
 * `mockResolvedValueOnce`），之後每一次呼叫都拿到同一個回應。`HomeScreen`
 * 接上 `home` 路由之後，登入成功會再打一次 `/elders`；那個情境要改用下面的
 * `mockByPath`，讓兩次呼叫各自拿到正確的回應，否則第二次呼叫會誤吃第一次
 * 的回應（登入回應物件被當成長輩陣列，`elders.map` 就炸了）。
 */
function mockAllRequests(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status, json: async () => body }));
}

/** 依請求路徑回不同的資料——登入成功後首頁會立刻打 /elders。 */
function mockByPath(map: Record<string, unknown>, status = 200) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation((path: string) => {
      const key = Object.keys(map).find((k) => String(path).includes(k));
      return Promise.resolve({
        status,
        json: async () => ({ success: true, data: key ? map[key] : null, error: null, meta: null }),
      });
    }),
  );
}

function failure(code: string, message: string) {
  return { success: false, data: null, error: { code, message }, meta: null };
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

describe("家屬登入", () => {
  it("未登入時顯示登入畫面", () => {
    renderApp();
    expect(screen.getByRole("heading", { name: "家屬登入" })).toBeInTheDocument();
  });

  it("登入成功後進到長輩列表", async () => {
    mockByPath({
      sessions: { guardian_id: "g1", name: "兒子", token: "tok" },
      elders: [],
    });
    renderApp();
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("heading", { name: "我的長輩" })).toBeInTheDocument();
  });

  it("帳密錯誤時顯示訊息，不把人踢走", async () => {
    mockAllRequests(401, failure("invalid_credentials", "帳號或密碼不正確"));
    renderApp();
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("帳號或密碼不對，請再試一次。");
    expect(screen.getByRole("heading", { name: "家屬登入" })).toBeInTheDocument();
  });

  // ⚠️ 非 401 的後端錯誤要照實顯示後端那句話，不可一律說成「連線失敗」。
  // 失效路徑：密碼欄留空按登入（前端沒擋）→ 後端 `min_length=1` 觸發 422 →
  // 回 `{code: "validation_error", message: "輸入資料格式不正確"}` → 畫面卻說
  // 「連線失敗，請稍後再試。」→ 使用者以為伺服器掛了，重按十次都一樣。
  // `ElderDetailScreen` 與 `SchedulesScreen` 早就是直接顯示 `exc.message` 的
  // ——同一條旅程的前兩步用了相反的原則。
  it("輸入格式不對時顯示後端那句話，而不是誤報成連線失敗", async () => {
    mockAllRequests(422, failure("validation_error", "輸入資料格式不正確"));
    renderApp();
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("輸入資料格式不正確");
  });

  it("真的連不上（不是後端回的錯）時才說連線失敗", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderApp();
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("連線失敗，請稍後再試。");
  });

  // ⚠️ 這條守的是「後端非 JSON 回應不可把英文字面值印給使用者看」。畢典當天
  // demo 對外走 Cloudflare Quick Tunnel，隧道抖動時回的是 502 的 HTML，不是
  // JSON；shared/client.ts 的 json() 解析失敗會自造 `http_502` / `HTTP 502`，
  // 若照實顯示 exc.message，家屬看到的就是「HTTP 502」而不是一句繁中的話。
  it("後端回非 JSON（如隧道抖動的 502）時說連線失敗，不印出 HTTP 502 這種英文字面值", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 502,
        json: async () => {
          throw new SyntaxError("Unexpected token '<'");
        },
      }),
    );
    renderApp();
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("連線失敗，請稍後再試。");
    expect(screen.queryByText(/HTTP 502/)).not.toBeInTheDocument();
  });

  it("已登入時第一次繪製就在長輩列表，不會先閃一次登入畫面", () => {
    // ⚠️ **不要**用 render() 斷言最終畫面：它內部用 act() 包住掛載、會把 effect
    // 一起 flush，所以「一律從登入起手、靠 effect 補到首頁」那種會閃一下的實作
    // 也會通過（本工項的變異驗證證實了這件事）。renderToString 完全不跑 effect，
    // 看到的就是第一次繪製的結果——那正是「會不會閃」的判準。
    localStorage.setItem(
      "kinsun_web_session_guardian",
      JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
    );
    const html = renderToString(
      <GuardianSession.Provider>
        <GuardianApp />
      </GuardianSession.Provider>,
    );
    expect(html).toContain("我的長輩");
    expect(html).not.toContain("家屬登入");
  });
});

describe("家屬註冊", () => {
  it("可以從登入頁切到註冊頁再切回來", async () => {
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "還沒有帳號？註冊" }));
    expect(screen.getByRole("heading", { name: "家屬註冊" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "已經有帳號？登入" }));
    expect(screen.getByRole("heading", { name: "家屬登入" })).toBeInTheDocument();
  });

  it("密碼太短時前端先擋下來，不打後端", async () => {
    const spy = vi.fn();
    vi.stubGlobal("fetch", spy);
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "還沒有帳號？註冊" }));
    await userEvent.type(screen.getByLabelText("您的稱呼"), "兒子");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "short");
    await userEvent.click(screen.getByRole("button", { name: "註冊並登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("密碼至少 8 碼。");
    expect(spy).not.toHaveBeenCalled();
  });

  it("Email 已註冊過時顯示可操作的訊息", async () => {
    // ⚠️ 409，不是 400：後端 `guardians.py` 對 `AppAccountError` 一律回 409。
    // 假回應與後端實況不符時，測試守的是一個不存在的世界。
    mockAllRequests(409, failure("email_taken", "這個 email 已經註冊過了"));
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "還沒有帳號？註冊" }));
    await userEvent.type(screen.getByLabelText("您的稱呼"), "兒子");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "註冊並登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "這個 Email 已經註冊過了，請直接登入。",
    );
  });

  // Email 打成 `abc`（漏 @）會被後端的 pattern 擋成 422。說成「連線失敗」會讓
  // 使用者去查網路，而真正要改的是他打錯的那一格。
  it("Email 格式不對時顯示後端那句話，而不是誤報成連線失敗", async () => {
    mockAllRequests(422, failure("validation_error", "輸入資料格式不正確"));
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "還沒有帳號？註冊" }));
    await userEvent.type(screen.getByLabelText("您的稱呼"), "兒子");
    await userEvent.type(screen.getByLabelText("Email"), "abc");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "註冊並登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("輸入資料格式不正確");
  });

  // 與登入頁同一個失效情境：隧道抖動回的 502 HTML 不是 JSON，不可把
  // shared/client.ts 自造的 `HTTP 502` 印給使用者看。
  it("後端回非 JSON（如隧道抖動的 502）時說連線失敗，不印出 HTTP 502 這種英文字面值", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        status: 502,
        json: async () => {
          throw new SyntaxError("Unexpected token '<'");
        },
      }),
    );
    renderApp();
    await userEvent.click(screen.getByRole("button", { name: "還沒有帳號？註冊" }));
    await userEvent.type(screen.getByLabelText("您的稱呼"), "兒子");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "註冊並登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("連線失敗，請稍後再試。");
    expect(screen.queryByText(/HTTP 502/)).not.toBeInTheDocument();
  });
});

describe("長輩詳情與返回", () => {
  // ⚠️ 這條釘住 GuardianApp 的 case "elder" 與 BackBar 兩件事：現有唯一碰
  // GuardianApp 的測試（上面兩個 describe）只走到 login／register／home 三個
  // 路由，從未點進長輩詳情頁、也從未按過返回鍵——把 canGoBack 改成 false、或把
  // case "elder" 整個拿掉，先前 138 條測試依然全線（已用變異驗證證實：見報告）。
  it("登入後點長輩可以看到詳情，按返回可以回到我的長輩", async () => {
    // ⚠️ key 順序刻意把較具體的路徑放前面：mockByPath 用 path.includes(key) 找
    // 第一個符合的 key，而 /elders/e1/health-report 這種子資源路徑本身就包含
    // "elders" 這個子字串——若 elders 排在前面，會讓三支長輩詳情的端點全部誤配
    // 到「長輩列表」那筆假資料（已實測：symptom 是 report.risk_events undefined）。
    mockByPath({
      sessions: { guardian_id: "g1", name: "兒子", token: "tok" },
      "health-report": { risk_events: [], reminders: [] },
      "daily-summaries": [],
      schedules: [],
      elders: [{ elder_id: "e1", name: "王阿嬤", nickname: "", persona: "lively_granddaughter" }],
    });
    renderApp();
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));

    await userEvent.click(await screen.findByRole("button", { name: /王阿嬤/ }));
    expect(await screen.findByRole("heading", { name: "王阿嬤" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "返回" }));
    expect(await screen.findByRole("heading", { name: "我的長輩" })).toBeInTheDocument();
  });
});
