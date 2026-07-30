/** 家屬註冊與登入。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

function mockOnce(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status, json: async () => body }));
}

function envelope(data: unknown) {
  return { success: true, data, error: null, meta: null };
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
    mockOnce(200, envelope({ guardian_id: "g1", name: "兒子", token: "tok" }));
    renderApp();
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "correct-horse-8");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("heading", { name: "我的長輩" })).toBeInTheDocument();
  });

  it("帳密錯誤時顯示訊息，不把人踢走", async () => {
    mockOnce(401, failure("invalid_credentials", "帳號或密碼不正確"));
    renderApp();
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("密碼"), "wrong-password");
    await userEvent.click(screen.getByRole("button", { name: "登入" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("帳號或密碼不對，請再試一次。");
    expect(screen.getByRole("heading", { name: "家屬登入" })).toBeInTheDocument();
  });

  it("重新掛載時記得已登入的身分", async () => {
    localStorage.setItem(
      "kinsun_web_session_guardian",
      JSON.stringify({ role: "guardian", token: "tok", display_name: "兒子" }),
    );
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ status: 200, json: async () => envelope([]) }));
    renderApp();
    expect(await screen.findByRole("heading", { name: "我的長輩" })).toBeInTheDocument();
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
    mockOnce(400, failure("email_taken", "這個 email 已經註冊過了"));
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
});
