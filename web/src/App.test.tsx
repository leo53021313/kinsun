/** 路由與階段轉換。 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function mockAvailable() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({
        success: true,
        data: { overall: "available", components: { asr: "ok" } },
        error: null,
        meta: null,
      }),
    }),
  );
}

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, "", "/demo/");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("一開始在開場頁", async () => {
    mockAvailable();
    render(<App />);
    expect(await screen.findByRole("button", { name: "開始使用" })).toBeInTheDocument();
  });

  it("按下開始使用後進到雙欄舞台", async () => {
    mockAvailable();
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: "開始使用" }));
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "長輩的手機" })).toBeInTheDocument();
    });
  });

  it("直接開舞台網址時不播動畫", async () => {
    mockAvailable();
    window.history.pushState({}, "", "/demo/stage");
    render(<App />);
    expect(await screen.findByRole("region", { name: "長輩的手機" })).toBeInTheDocument();
    expect(screen.queryByTestId("tear-left")).not.toBeInTheDocument();
  });
});
