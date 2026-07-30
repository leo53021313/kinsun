/**
 * 雙角色 session。
 *
 * ⚠️ 這是本前端與 App 最根本的差異：App 的 SessionProvider 是掛在根節點的
 * 單例，一個分頁只有一份登入狀態。左右兩欄要**同時各自登入**，所以改為工廠。
 * 「兩欄互不干擾」是這裡最重要的一條測試——它壞掉的症狀是「登入右邊，左邊
 * 也跟著變了」，那會讓整個雙欄展示失去意義。
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "kinsun-shared/envelope";

import { createSessionContext } from "./createSessionContext";
import { clearSession, loadSession, saveSession, type Session } from "./storage";
import { makeSignOutOnAuthError } from "./useSignOutOnAuthError";

const Elder = createSessionContext("elder");
const Guardian = createSessionContext("guardian");

function Panel(props: { ctx: typeof Elder; label: string }) {
  const { session, signIn, signOut } = props.ctx.useSession();
  return (
    <div>
      <p>
        {props.label}：{session ? session.display_name : "未登入"}
      </p>
      <button
        onClick={() =>
          signIn({ token: `${props.label}-token`, display_name: `${props.label}的人` })
        }
      >
        登入{props.label}
      </button>
      <button onClick={() => void signOut()}>登出{props.label}</button>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
});

describe("storage", () => {
  it("存讀同一個角色的 session", () => {
    saveSession({ role: "elder", token: "t1", display_name: "王阿嬤" });
    expect(loadSession("elder")?.display_name).toBe("王阿嬤");
  });

  it("兩個角色各存各的，不共用一個鍵", () => {
    saveSession({ role: "elder", token: "t1", display_name: "王阿嬤" });
    saveSession({ role: "guardian", token: "t2", display_name: "兒子" });
    expect(loadSession("elder")?.token).toBe("t1");
    expect(loadSession("guardian")?.token).toBe("t2");
  });

  it("清掉一個角色不影響另一個", () => {
    saveSession({ role: "elder", token: "t1", display_name: "王阿嬤" });
    saveSession({ role: "guardian", token: "t2", display_name: "兒子" });
    clearSession("elder");
    expect(loadSession("elder")).toBeNull();
    expect(loadSession("guardian")?.token).toBe("t2");
  });

  it("存的內容壞掉時當作沒登入，而不是整頁爆掉", () => {
    localStorage.setItem("kinsun_web_session_elder", "{壞掉的 JSON");
    expect(loadSession("elder")).toBeNull();
  });
});

describe("createSessionContext", () => {
  it("兩欄各自登入，互不干擾", async () => {
    render(
      <Elder.Provider>
        <Guardian.Provider>
          <Panel ctx={Elder} label="左" />
          <Panel ctx={Guardian} label="右" />
        </Guardian.Provider>
      </Elder.Provider>,
    );
    expect(screen.getByText("左：未登入")).toBeInTheDocument();
    expect(screen.getByText("右：未登入")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "登入右" }));
    expect(screen.getByText("右：右的人")).toBeInTheDocument();
    expect(screen.getByText("左：未登入")).toBeInTheDocument();
  });

  it("登出一欄不影響另一欄", async () => {
    render(
      <Elder.Provider>
        <Guardian.Provider>
          <Panel ctx={Elder} label="左" />
          <Panel ctx={Guardian} label="右" />
        </Guardian.Provider>
      </Elder.Provider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "登入左" }));
    await userEvent.click(screen.getByRole("button", { name: "登入右" }));
    await userEvent.click(screen.getByRole("button", { name: "登出左" }));
    expect(screen.getByText("左：未登入")).toBeInTheDocument();
    expect(screen.getByText("右：右的人")).toBeInTheDocument();
  });

  it("重新掛載時把存著的登入讀回來", () => {
    saveSession({ role: "elder", token: "t1", display_name: "王阿嬤" });
    render(
      <Elder.Provider>
        <Panel ctx={Elder} label="左" />
      </Elder.Provider>,
    );
    expect(screen.getByText("左：王阿嬤")).toBeInTheDocument();
  });

  it("登入的角色由 context 自己決定，token 只落在自己的鍵", async () => {
    render(
      <Elder.Provider>
        <Panel ctx={Elder} label="左" />
      </Elder.Provider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "登入左" }));
    expect(loadSession("elder")).toEqual({
      role: "elder",
      token: "左-token",
      display_name: "左的人",
    });
    expect(localStorage.getItem("kinsun_web_session_guardian")).toBeNull();
  });

  it("呼叫端硬塞角色也蓋不掉 context 自己的角色", async () => {
    // ⚠️ 這是「兩欄互不干擾」唯一可被違反的路徑。以前 signIn 收整個 Session、
    // 寫入那一路用的是 `next.role`（讀取與清除卻用工廠的 role）：在長輩 context 上
    // 傳成 guardian，畫面會顯示長輩已登入，token 卻落在家屬鍵、長輩鍵是 null。
    // 重整之後家屬欄變成登入、長輩欄空白——看起來像永久故障。
    //
    // 型別現在已經擋住了（signIn 收 Omit<Session, "role">），這裡用 cast 模擬繞過
    // 型別的呼叫端——守的是 `saveSession({ ...next, role })` 裡 role 放在後面這個
    // 順序，寫成 `{ role, ...next }` 的話同一個 bug 會原地復活。
    function Rogue() {
      const forced = Elder.useSession().signIn as unknown as (next: Session) => void;
      return (
        <button onClick={() => forced({ role: "guardian", token: "t", display_name: "冒名" })}>
          亂傳
        </button>
      );
    }
    render(
      <Elder.Provider>
        <Rogue />
      </Elder.Provider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "亂傳" }));
    expect(loadSession("elder")?.display_name).toBe("冒名");
    expect(loadSession("elder")?.role).toBe("elder");
    expect(localStorage.getItem("kinsun_web_session_guardian")).toBeNull();
  });

  it("在 Provider 外面用 hook 會擲出說得清楚的錯誤", () => {
    function Orphan() {
      Elder.useSession();
      return null;
    }
    expect(() => render(<Orphan />)).toThrow(/Provider/);
  });

  it("已存的登入在第一次繪製就讀得到，不會先閃一次未登入", () => {
    // ⚠️ 這一條守的是 lazy initializer（`useState(() => loadSession(role))`）。
    // 若改成在 effect 裡讀，元件會先以 null 繪製一次、effect 跑完再繪製一次——
    // 兩欄同時閃一次「未登入」很難看。
    //
    // ⚠️ 必須記錄「每一次繪製看到什麼」而不是斷言最終畫面：testing-library 的
    // render() 內部用同步 act() 包住掛載，會把 effect 一起 flush 掉，所以兩種
    // 實作的最終畫面一模一樣，只看結果分辨不出來。
    saveSession({ role: "elder", token: "t1", display_name: "王阿嬤" });
    const seen: (Session | null)[] = [];
    function Probe() {
      seen.push(Elder.useSession().session);
      return null;
    }
    render(
      <Elder.Provider>
        <Probe />
      </Elder.Provider>,
    );
    expect(seen).toEqual([{ role: "elder", token: "t1", display_name: "王阿嬤" }]);
  });
});

describe("makeSignOutOnAuthError", () => {
  it("401 時登出並回報已處理", () => {
    const signOut = vi.fn();
    expect(makeSignOutOnAuthError(signOut)(new ApiError(401, "invalid_token"))).toBe(true);
    expect(signOut).toHaveBeenCalledOnce();
  });

  it("其他錯誤不登出，交回給呼叫端顯示", () => {
    const signOut = vi.fn();
    expect(makeSignOutOnAuthError(signOut)(new ApiError(400, "name_required"))).toBe(false);
    expect(makeSignOutOnAuthError(signOut)(new Error("network"))).toBe(false);
    expect(signOut).not.toHaveBeenCalled();
  });
});
