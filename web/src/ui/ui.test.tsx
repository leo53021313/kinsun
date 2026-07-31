/** 共用原子元件：可及性與狀態。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";
import { EmptyHint, ErrorText, NoticeText } from "./Feedback";
import { Field } from "./Field";
import { Section } from "./Section";

describe("Button", () => {
  it("按下去會呼叫 onClick", async () => {
    const onClick = vi.fn();
    render(<Button label="送出" onClick={onClick} />);
    await userEvent.click(screen.getByRole("button", { name: "送出" }));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("忙碌中不可點，且不會重複送出", async () => {
    // 家屬連按兩下「建立長輩檔案」會建出兩位長輩——這一條擋的就是那個。
    const onClick = vi.fn();
    render(<Button label="送出" onClick={onClick} busy />);
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    await userEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("忙碌中要讓人看得出來在忙", () => {
    render(<Button label="送出" onClick={vi.fn()} busy />);
    expect(screen.getByRole("button")).toHaveAttribute("aria-busy", "true");
  });

  it("停用時不可點", () => {
    render(<Button label="送出" onClick={vi.fn()} disabled />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});

describe("Field", () => {
  it("標籤與輸入框有連起來，點標籤會聚焦到輸入框", async () => {
    render(<Field label="長輩稱呼" value="" onChange={vi.fn()} />);
    const input = screen.getByLabelText("長輩稱呼");
    await userEvent.click(screen.getByText("長輩稱呼"));
    expect(input).toHaveFocus();
  });

  it("輸入時回報新的值", async () => {
    const onChange = vi.fn();
    render(<Field label="長輩稱呼" value="" onChange={onChange} />);
    await userEvent.type(screen.getByLabelText("長輩稱呼"), "阿");
    expect(onChange).toHaveBeenLastCalledWith("阿");
  });

  it("size=\"big\" 時標籤也要跟著放大，不能停在 14px", () => {
    // ⚠️ 審查發現：標籤原本固定 text-sm（14px），不隨 size="big" 放大——
    // 輸入框內文是 22px，但「綁定碼」「手機號碼」「密碼」這些一直掛在畫面上
    // 的標籤反而是全畫面最小的字。
    render(<Field label="綁定碼" value="" onChange={vi.fn()} size="big" />);
    const label = screen.getByText("綁定碼");
    expect(label).toHaveClass("text-elder-min");
    expect(label).not.toHaveClass("text-sm");
  });

  it("size 預設（家屬端）標籤維持原本的 text-sm，不被連帶放大", () => {
    render(<Field label="長輩稱呼" value="" onChange={vi.fn()} />);
    expect(screen.getByText("長輩稱呼")).toHaveClass("text-sm");
  });

  it("同一個畫面上的兩個欄位拿到不同的 id", () => {
    // ⚠️ **不要**用「點標籤看誰拿到焦點」來驗這件事：id 重複時，jsdom 的
    // `label.control` 與 testing-library 的 `getByLabelText` 用的是同一套
    // 「取 DOM 順序第一個」的解析，兩者永遠自洽——那樣的測試在 id 寫死時
    // 照樣會通過（P2 審查追進兩者原始碼實測確認）。直接斷言 id 本身才有辨別力。
    //
    // 這條守的是 Field 用 useId 而非寫死 id。寫死的話，點標籤永遠聚焦到第一個
    // 欄位，而那種 bug 用眼睛看不出來。
    const { container } = render(
      <>
        <Field label="密碼" value="" onChange={vi.fn()} type="password" />
        <Field label="確認密碼" value="" onChange={vi.fn()} type="password" />
      </>,
    );
    const inputs = Array.from(container.querySelectorAll("input"));
    const labels = Array.from(container.querySelectorAll("label"));
    expect(inputs).toHaveLength(2);
    expect(inputs[0].id).toBeTruthy();
    expect(inputs[1].id).toBeTruthy();
    expect(inputs[0].id).not.toBe(inputs[1].id);
    // 每個標籤都指向自己那一個輸入框
    expect(labels[0].getAttribute("for")).toBe(inputs[0].id);
    expect(labels[1].getAttribute("for")).toBe(inputs[1].id);
  });
});

describe("Feedback", () => {
  it("沒有訊息時 ErrorText 什麼都不畫", () => {
    const { container } = render(<ErrorText message="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("有訊息時以 alert 角色呈現，讀螢幕的人才會被告知", () => {
    render(<ErrorText message="帳號或密碼不對，請再試一次。" />);
    expect(screen.getByRole("alert")).toHaveTextContent("帳號或密碼不對，請再試一次。");
  });

  it("size 預設是 text-sm（14px），家屬端沿用既有字級不受影響", () => {
    render(<ErrorText message="帳號或密碼不對，請再試一次。" />);
    expect(screen.getByRole("alert")).toHaveClass("text-sm");
  });

  it("size=\"big\" 時放大到長輩端最小字級，不能停在 14px", () => {
    // ⚠️ 審查發現：本任務整個主題（五種綁定錯誤＋六種相機錯誤，那十一句
    // 「告訴他下一步做什麼」的話）原本全部以 14px（text-sm）呈現——是全畫面
    // 最小的字。
    render(<ErrorText message="這組號碼是給家人用的，請家人給您長輩專用的那組。" size="big" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("text-elder-min");
    expect(alert).not.toHaveClass("text-sm");
  });

  it("EmptyHint 顯示提示文字", () => {
    render(<EmptyHint text="目前沒有通知。" />);
    expect(screen.getByText("目前沒有通知。")).toBeInTheDocument();
  });

  it("沒有訊息時 NoticeText 什麼都不畫", () => {
    const { container } = render(<NoticeText message="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("NoticeText 不是警示：用 status 而非 alert，才不會被當警告打斷朗讀", () => {
    render(<NoticeText message="已設定完成。" />);
    expect(screen.getByRole("status")).toHaveTextContent("已設定完成。");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Section", () => {
  it("標題以 heading 呈現，讀螢幕的人才能跳著看", () => {
    render(
      <Section title="新增長輩">
        <p>內容</p>
      </Section>,
    );
    expect(screen.getByRole("heading", { name: "新增長輩" })).toBeInTheDocument();
    expect(screen.getByText("內容")).toBeInTheDocument();
  });
});
