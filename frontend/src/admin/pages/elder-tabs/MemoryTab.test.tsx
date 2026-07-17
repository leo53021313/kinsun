/**
 * MemoryTab 的釘樁測試（characterization test）。
 *
 * ⚠️ 它的用途不只是測 MemoryTab：七頁遷移到 useLoadable 之後，本檔仍須綠——
 * 那就是「重構沒有改壞行為」的證據。故本檔刻意只斷言使用者看得到的東西
 * （畫面上的字），不碰任何內部實作，才能跨越重構存活。
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getElderMemory } from "../../api";
import { MemoryTab } from "./MemoryTab";

vi.mock("../../api", () => ({
  getElderMemory: vi.fn(),
}));

function renderTab() {
  return render(
    <MemoryRouter initialEntries={["/elders/e1/memory"]}>
      <Routes>
        <Route path="/elders/:elderId/memory" element={<MemoryTab />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("MemoryTab", () => {
  beforeEach(() => {
    vi.mocked(getElderMemory).mockReset();
  });

  it("載入成功時顯示長期記憶內容", async () => {
    vi.mocked(getElderMemory).mockResolvedValue({
      memories: [{ text: "阿公喜歡吃滷肉飯", provenance: "自述", date: "2026-07-10" }],
      summaries: [],
    });

    renderTab();

    expect(await screen.findByText(/阿公喜歡吃滷肉飯/)).toBeInTheDocument();
  });

  it("載入失敗時顯示錯誤橫幅", async () => {
    vi.mocked(getElderMemory).mockRejectedValue(new Error("boom"));

    renderTab();

    expect(await screen.findByText("載入失敗，請重新整理。")).toBeInTheDocument();
  });

  it("載入完成前顯示載入中", () => {
    vi.mocked(getElderMemory).mockReturnValue(new Promise(() => {}));

    renderTab();

    expect(screen.getByText("載入中…")).toBeInTheDocument();
  });
});
