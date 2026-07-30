/**
 * 框內畫面堆疊。
 *
 * ⚠️ 為什麼不用 react-router：兩欄同時存在，各有各的畫面深度。讓它們去搶同一條
 * 瀏覽器網址只會互相覆蓋——右欄進到排程頁，左欄的網址也跟著變。
 */

import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { useScreenStack } from "./useScreenStack";

type Route = { name: string };

function Harness() {
  const stack = useScreenStack<Route>({ name: "home" });
  return (
    <div>
      <p>目前：{stack.current.name}</p>
      <p>深度：{stack.depth}</p>
      <button onClick={() => stack.push({ name: "detail" })}>前進</button>
      <button onClick={() => stack.back()}>返回</button>
      <button onClick={() => stack.reset({ name: "login" })}>重設</button>
    </div>
  );
}

describe("useScreenStack", () => {
  it("一開始在起始畫面，深度為一", () => {
    render(<Harness />);
    expect(screen.getByText("目前：home")).toBeInTheDocument();
    expect(screen.getByText("深度：1")).toBeInTheDocument();
  });

  it("前進之後可以返回", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "前進" }));
    expect(screen.getByText("目前：detail")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "返回" }));
    expect(screen.getByText("目前：home")).toBeInTheDocument();
  });

  it("在最底層按返回不會把畫面清空", async () => {
    // 沒有這道保護的話，堆疊會變成空的、current 變 undefined，整欄白畫面。
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "返回" }));
    expect(screen.getByText("目前：home")).toBeInTheDocument();
    expect(screen.getByText("深度：1")).toBeInTheDocument();
  });

  it("重設會清掉整個堆疊", async () => {
    render(<Harness />);
    await userEvent.click(screen.getByRole("button", { name: "前進" }));
    await userEvent.click(screen.getByRole("button", { name: "重設" }));
    expect(screen.getByText("目前：login")).toBeInTheDocument();
    expect(screen.getByText("深度：1")).toBeInTheDocument();
  });
});
