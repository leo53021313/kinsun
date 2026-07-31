/** 手機外框：內容區、可及性標題、通知橫幅的容身處。 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PhoneFrame } from "./PhoneFrame";

describe("PhoneFrame", () => {
  it("顯示框內的內容", () => {
    render(
      <PhoneFrame title="長輩的手機" os="ios">
        <p>對講機</p>
      </PhoneFrame>,
    );
    expect(screen.getByText("對講機")).toBeInTheDocument();
  });

  it("以標題標示這是誰的手機，讀螢幕的人才分得出兩欄", () => {
    render(
      <PhoneFrame title="家屬的手機" os="android">
        <p>首頁</p>
      </PhoneFrame>,
    );
    expect(screen.getByRole("region", { name: "家屬的手機" })).toBeInTheDocument();
  });

  it("iOS 外框有動態島，Android 沒有", () => {
    const { rerender } = render(
      <PhoneFrame title="A" os="ios">
        <p>x</p>
      </PhoneFrame>,
    );
    expect(screen.getByTestId("dynamic-island")).toBeInTheDocument();
    rerender(
      <PhoneFrame title="A" os="android">
        <p>x</p>
      </PhoneFrame>,
    );
    expect(screen.queryByTestId("dynamic-island")).not.toBeInTheDocument();
  });

  it("留了通知橫幅的位置", () => {
    render(
      <PhoneFrame title="A" os="ios" notificationSlot={<p>提醒您吃藥</p>}>
        <p>x</p>
      </PhoneFrame>,
    );
    expect(screen.getByText("提醒您吃藥")).toBeInTheDocument();
  });

  it("通知容身處一律是 status live region，不管有沒有通知內容", () => {
    // ⚠️ 審查修正（2026-07-31）：live region 要在通知內容出現「之前」就已經
    // 存在，輔助科技才追得到之後的文字變化——這顆容器從 PhoneFrame 掛載那
    // 一刻就在，不隨 notificationSlot 有沒有內容而增減。
    render(
      <PhoneFrame title="A" os="ios">
        <p>x</p>
      </PhoneFrame>,
    );
    expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
  });

  it("有通知內容時，live region 是容身處自己的，內容只是放在裡面", () => {
    render(
      <PhoneFrame title="A" os="ios" notificationSlot={<p>提醒您吃藥</p>}>
        <p>x</p>
      </PhoneFrame>,
    );
    expect(screen.getByRole("status")).toContainElement(screen.getByText("提醒您吃藥"));
  });

  it("狀態列不是真的時間_是固定的展示用文字", () => {
    // 展示畫面上跳動的時鐘會把觀眾的注意力吸走，而且截圖會因此每張都不一樣。
    render(
      <PhoneFrame title="A" os="ios">
        <p>x</p>
      </PhoneFrame>,
    );
    expect(screen.getByText("9:41")).toBeInTheDocument();
  });
});
