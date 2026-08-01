/** 開場頁：按鈕的可點性與分項燈號。
 *
 * ⚠️ 狀態由 props 灌進來（本元件是純展示，見 GatePage.tsx 的說明），所以這裡完全
 * 不必 mock fetch。輪詢與錯誤處理那一路歸 useDemoStatus.test.ts。
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { GatePage } from "./GatePage";
import type { GateState } from "./useDemoStatus";

function state(overall: string, components: Record<string, string> = {}): GateState {
  return { status: { overall, components }, unreachable: false };
}

describe("GatePage", () => {
  it("服務正常時按鈕可以按", async () => {
    const onStart = vi.fn();
    render(<GatePage state={state("available", { asr: "ok", tts: "ok" })} onStart={onStart} />);
    const button = screen.getByRole("button", { name: "開始使用" });
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(onStart).toHaveBeenCalledOnce();
  });

  it("服務停機時按鈕不能按", () => {
    render(<GatePage state={state("down", { database: "down" })} onStart={vi.fn()} />);
    expect(screen.getByText("服務目前無法使用")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "開始使用" })).toBeDisabled();
  });

  it("啟動中時按鈕不能按", () => {
    render(<GatePage state={state("starting", { asr: "loading" })} onStart={vi.fn()} />);
    expect(screen.getByText("服務正在啟動，請稍候…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "開始使用" })).toBeDisabled();
  });

  it("部分受限時可以進入，並說清楚少了什麼", () => {
    render(<GatePage state={state("degraded", { asr: "ok", tts: "down" })} onStart={vi.fn()} />);
    expect(
      screen.getByText("金孫聽得懂您說話，但暫時不會出聲，回答只會顯示文字。"),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "開始使用" })).toBeEnabled();
  });

  it("還沒問到結果時顯示確認中，按鈕不能按", () => {
    render(<GatePage state={{ status: null, unreachable: false }} onStart={vi.fn()} />);
    expect(screen.getByText("正在確認服務狀態…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "開始使用" })).toBeDisabled();
  });

  it("連不上後端時說的是伺服器沒開，不是服務停機", () => {
    render(<GatePage state={{ status: null, unreachable: true }} onStart={vi.fn()} />);
    expect(screen.getByText("連不上服務，可能是伺服器沒有啟動。")).toBeInTheDocument();
  });

  it("逐項顯示分項狀態", () => {
    render(
      <GatePage
        state={state("degraded", { asr: "ok", tts: "down", scheduler: "unknown" })}
        onStart={vi.fn()}
      />,
    );
    expect(screen.getByText("聽懂您說話")).toBeInTheDocument();
    expect(screen.getByText("開口說話")).toBeInTheDocument();
    expect(screen.getByText("準時提醒")).toBeInTheDocument();
  });
});
