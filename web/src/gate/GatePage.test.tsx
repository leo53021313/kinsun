/** 開場頁：按鈕的可點性與分項燈號。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GatePage } from "./GatePage";

function mockStatus(overall: string, components: Record<string, string> = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      status: 200,
      json: async () => ({
        success: true,
        data: { overall, components },
        error: null,
        meta: null,
      }),
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("GatePage", () => {
  it("服務正常時按鈕可以按", async () => {
    mockStatus("available", { asr: "ok", tts: "ok" });
    const onStart = vi.fn();
    render(<GatePage onStart={onStart} />);
    const button = await screen.findByRole("button", { name: "開始使用" });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(onStart).toHaveBeenCalledOnce();
  });

  it("服務停機時按鈕不能按", async () => {
    mockStatus("down", { database: "down" });
    const onStart = vi.fn();
    render(<GatePage onStart={onStart} />);
    expect(await screen.findByText("服務目前無法使用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "開始使用" })).toBeDisabled();
  });

  it("啟動中時按鈕不能按", async () => {
    mockStatus("starting", { asr: "loading" });
    render(<GatePage onStart={vi.fn()} />);
    expect(await screen.findByText("服務正在啟動，請稍候…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "開始使用" })).toBeDisabled();
  });

  it("部分受限時可以進入，並說清楚少了什麼", async () => {
    mockStatus("degraded", { asr: "ok", tts: "down" });
    render(<GatePage onStart={vi.fn()} />);
    expect(
      await screen.findByText("金孫聽得懂您說話，但暫時不會出聲，回答只會顯示文字。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "開始使用" })).toBeEnabled();
  });

  it("連不上後端時說的是伺服器沒開，不是服務停機", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));
    render(<GatePage onStart={vi.fn()} />);
    expect(
      await screen.findByText("連不上服務，可能是伺服器沒有啟動。"),
    ).toBeInTheDocument();
  });

  it("逐項顯示分項狀態", async () => {
    mockStatus("degraded", { asr: "ok", tts: "down", scheduler: "unknown" });
    render(<GatePage onStart={vi.fn()} />);
    expect(await screen.findByText("聽懂您說話")).toBeInTheDocument();
    expect(screen.getByText("開口說話")).toBeInTheDocument();
    expect(screen.getByText("準時提醒")).toBeInTheDocument();
  });
});
