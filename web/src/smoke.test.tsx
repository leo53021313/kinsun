/** 工具鏈驗證：React 渲染得動、jsdom 在、jest-dom 斷言掛上了、shared 引得到。 */

import { render, screen } from "@testing-library/react";
import { formatTime } from "kinsun-shared/format";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, "", "/demo/");
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
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("工具鏈", () => {
  it("渲染得動 React 元件", async () => {
    render(<App />);
    expect(await screen.findByText("金孫")).toBeInTheDocument();
  });

  it("引得到共用包 kinsun-shared", () => {
    // 2026-01-02 08:05 (UTC+8) 的 epoch 秒。formatTime 用本機時區，
    // 故只斷言格式而非確切數值——CI 與開發機時區不一定相同。
    expect(formatTime(1735776300)).toMatch(/^\d{1,2}\/\d{1,2} \d{2}:\d{2}$/);
  });
});
