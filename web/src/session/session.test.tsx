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
import { beforeEach, describe, expect, it } from "vitest";

import { createSessionContext } from "./createSessionContext";
import { clearSession, loadSession, saveSession } from "./storage";

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
          signIn({
            role: session?.role ?? (props.label === "左" ? "elder" : "guardian"),
            token: `${props.label}-token`,
            display_name: `${props.label}的人`,
          })
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

  it("在 Provider 外面用 hook 會擲出說得清楚的錯誤", () => {
    function Orphan() {
      Elder.useSession();
      return null;
    }
    expect(() => render(<Orphan />)).toThrow(/Provider/);
  });
});
