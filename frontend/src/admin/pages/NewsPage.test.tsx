import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listNews } from "../api";
import { NewsPage } from "./NewsPage";

vi.mock("../api", () => ({
  listNews: vi.fn(),
}));

describe("NewsPage", () => {
  beforeEach(() => {
    vi.mocked(listNews).mockReset();
  });

  it("載入成功時顯示新聞列表（標題連到原文）", async () => {
    vi.mocked(listNews).mockResolvedValue([
      {
        news_item_id: "n1",
        source_id: "mohw",
        title: "長者防跌新措施",
        url: "https://example.com/n1",
        publisher: "衛生福利部",
        published_at: 1_785_000_000,
        retrieved_at: 1_785_003_600,
      },
    ]);

    render(<NewsPage />);

    const link = await screen.findByRole("link", { name: "長者防跌新措施" });
    expect(link).toHaveAttribute("href", "https://example.com/n1");
    expect(screen.getByText("衛生福利部")).toBeInTheDocument();
  });

  it("沒有新聞時顯示空狀態提示（含手動觸發指引）", async () => {
    vi.mocked(listNews).mockResolvedValue([]);

    render(<NewsPage />);

    expect(await screen.findByText(/沒有爬到新聞/)).toBeInTheDocument();
  });

  it("載入失敗時顯示錯誤橫幅", async () => {
    vi.mocked(listNews).mockRejectedValue(new Error("boom"));

    render(<NewsPage />);

    expect(await screen.findByText("載入失敗，請重新整理。")).toBeInTheDocument();
  });
});
