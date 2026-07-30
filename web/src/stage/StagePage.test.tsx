/** 雙欄舞台：兩欄都在、窄螢幕以頁籤切換。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { StagePage } from "./StagePage";

beforeEach(() => {
  localStorage.clear();
});

describe("StagePage", () => {
  it("兩支手機同時在畫面上", () => {
    render(<StagePage />);
    expect(screen.getByRole("region", { name: "長輩的手機" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "家屬的手機" })).toBeInTheDocument();
  });

  it("窄螢幕的切換頁籤兩個都在", () => {
    render(<StagePage />);
    expect(screen.getByRole("tab", { name: "長輩端" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "家屬端" })).toBeInTheDocument();
  });

  it("預設選中長輩端", () => {
    render(<StagePage />);
    expect(screen.getByRole("tab", { name: "長輩端" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "家屬端" })).toHaveAttribute("aria-selected", "false");
  });

  it("點頁籤可以切換", async () => {
    render(<StagePage />);
    await userEvent.click(screen.getByRole("tab", { name: "家屬端" }));
    expect(screen.getByRole("tab", { name: "家屬端" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "長輩端" })).toHaveAttribute("aria-selected", "false");
  });
});
