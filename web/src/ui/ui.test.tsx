/** 共用原子元件：可及性與狀態。 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";
import { EmptyHint, ErrorText } from "./Feedback";
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

  it("同一個畫面上兩個同名欄位不會互相搶焦點", async () => {
    // id 若寫死，兩個 Field 會產生重複的 id，點標籤永遠聚焦到第一個。
    render(
      <>
        <Field label="密碼" value="" onChange={vi.fn()} type="password" />
        <Field label="確認密碼" value="" onChange={vi.fn()} type="password" />
      </>,
    );
    await userEvent.click(screen.getByText("確認密碼"));
    expect(screen.getByLabelText("確認密碼")).toHaveFocus();
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

  it("EmptyHint 顯示提示文字", () => {
    render(<EmptyHint text="目前沒有通知。" />);
    expect(screen.getByText("目前沒有通知。")).toBeInTheDocument();
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
