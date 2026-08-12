/** 「之前聊過的」：只留當天、最新在最上面、固定頁首只捲內容。 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { HistoryScreen } from "./HistoryScreen";
import { appendTurn } from "./todayLog";

beforeEach(() => localStorage.clear());

function renderScreen() {
  const onBack = vi.fn();
  render(<HistoryScreen onBack={onBack} />);
  return { onBack };
}

describe("HistoryScreen", () => {
  it("講三句之後看得到三則，最新的在最上面", async () => {
    // 長輩要找的通常是剛才那句，不是今天第一句。
    await appendTurn({ at: 1_754_000_000_000, said: "第一句", reply: "回一" });
    await appendTurn({ at: 1_754_000_060_000, said: "第二句", reply: "回二" });
    await appendTurn({ at: 1_754_000_120_000, said: "第三句", reply: "回三" });
    renderScreen();

    await waitFor(() => expect(screen.getByTestId("history-turn-0")).toBeInTheDocument());
    expect(screen.getByTestId("history-turn-0")).toHaveTextContent("第三句");
    expect(screen.getByTestId("history-turn-2")).toHaveTextContent("第一句");
  });

  it("兩行分別標明是誰講的", async () => {
    await appendTurn({ at: 1_754_000_000_000, said: "今天天氣真好", reply: "是啊" });
    renderScreen();
    const card = await screen.findByTestId("history-turn-0");
    expect(card).toHaveTextContent("您說：今天天氣真好");
    expect(card).toHaveTextContent("阿白說：是啊");
  });

  it("今天還沒聊過時給一句話告訴他下一步，不是空白畫面", async () => {
    renderScreen();
    expect(
      await screen.findByText("今天還沒聊過。按下面的麥克風跟我說說話吧。"),
    ).toBeInTheDocument();
    // 空的時候不出現「只留今天的」那句——沒東西可留，講了只會讓人困惑。
    expect(screen.queryByText("只留今天的，明天就換新的了。")).not.toBeInTheDocument();
  });

  it("隔天打開是空的", async () => {
    // 「只留當天」：跨日自動視為空，不必等清除排程。
    localStorage.setItem(
      "kinsun.todayLog.v1",
      JSON.stringify({
        day: "2020-01-01",
        turns: [{ at: 1, said: "昨天說的", reply: "昨天回的" }],
      }),
    );
    renderScreen();
    expect(
      await screen.findByText("今天還沒聊過。按下面的麥克風跟我說說話吧。"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/昨天說的/)).not.toBeInTheDocument();
  });

  it("沒有「再聽一次」——依 2026-08-07 選項 1，沒有真實音檔契約前不放無作用的鈕", async () => {
    await appendTurn({ at: 1_754_000_000_000, said: "今天天氣真好", reply: "是啊" });
    renderScreen();
    await screen.findByTestId("history-turn-0");
    expect(screen.queryByRole("button", { name: /再聽/ })).not.toBeInTheDocument();
  });

  it("返回鈕回對講機，且是 60dp 的圓鈕", async () => {
    const h = renderScreen();
    const back = screen.getByRole("button", { name: "回去講話" });
    expect(back.className).toContain("size-[var(--size-elder-round-button)]");
    await userEvent.click(back);
    expect(h.onBack).toHaveBeenCalledOnce();
  });

  it("頁首固定，只有內容層捲動", async () => {
    // 規則 2 的例外只開給內容層：一天講幾十輪，清單一定超過一屏。
    renderScreen();
    const list = await screen.findByTestId("history-list");
    expect(list.className).toContain("overflow-y-auto");
    expect(list.className).toContain("min-h-0");
  });

  it("字級全部不低於長輩端下限", async () => {
    // ⚠️ 斷言 class 而非實際尺寸：jsdom 沒有版面計算。真正的視覺由人工驗收把關。
    await appendTurn({ at: 1_754_000_000_000, said: "今天天氣真好", reply: "是啊" });
    renderScreen();
    const card = await screen.findByTestId("history-turn-0");
    for (const line of Array.from(card.querySelectorAll("p"))) {
      expect(line.className).toContain("text-elder-min");
    }
  });
});
