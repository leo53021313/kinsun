import { fireEvent, render } from "@testing-library/react-native";
import { StyleSheet, Text } from "react-native";

import { Button, Chip, ErrorText, Field, Section, StatusPill } from "@/components/ui";
import { colors, elder, radius } from "@/lib/theme";

describe("共用 UI 元件", () => {
  it("主要按鈕使用暖黃膠囊，busy 時保留動作名稱並停用", async () => {
    const onPress = jest.fn();
    const screen = await render(<Button label="建立長輩檔案" onPress={onPress} busy />);
    const button = screen.getByRole("button");

    expect(screen.getByText("建立長輩檔案")).toBeTruthy();
    expect(button.props.accessibilityState).toEqual({ busy: true, disabled: true });
    expect(StyleSheet.flatten(button.props.style)).toMatchObject({
      backgroundColor: colors.action,
      borderRadius: radius.pill,
      minHeight: 56,
      opacity: 0.5,
    });
    await fireEvent.press(button);
    expect(onPress).not.toHaveBeenCalled();
  });

  it("長輩大按鈕固定 84dp，文字不設字級放大上限", async () => {
    const screen = await render(<Button label="開始使用" onPress={jest.fn()} size="big" />);

    expect(StyleSheet.flatten(screen.getByRole("button").props.style).minHeight).toBe(84);
    const label = screen.getByText("開始使用");
    expect(StyleSheet.flatten(label.props.style).fontSize).toBe(elder.fontBig);
    expect(label.props.maxFontSizeMultiplier).toBeUndefined();
  });

  it("鍵盤 focus 會顯示 2px 描邊與 2px 外偏移", async () => {
    const screen = await render(<Button label="儲存" onPress={jest.fn()} />);
    const button = screen.getByRole("button");

    await fireEvent(button, "focus");
    expect(StyleSheet.flatten(screen.getByRole("button").props.style)).toMatchObject({
      borderColor: colors.primary,
      borderWidth: 2,
      outlineColor: colors.primary,
      outlineOffset: 2,
      outlineWidth: 2,
    });
  });

  it("Field 的 hint 與 big 字級符合長輩下限，標籤會連到輸入框", async () => {
    const screen = await render(
      <Field label="手機號碼" hint="例如：0912345678" value="" size="big" />,
    );

    const input = screen.getByLabelText("手機號碼");
    const label = screen.getByText("手機號碼");
    const hint = screen.getByText("例如：0912345678");
    expect(StyleSheet.flatten(label.props.style).fontSize).toBe(elder.fontMin);
    expect(StyleSheet.flatten(hint.props.style).fontSize).toBe(elder.fontMin);
    expect(StyleSheet.flatten(input.props.style).fontSize).toBe(elder.fontMin);
    expect(label.props.maxFontSizeMultiplier).toBeUndefined();
  });

  it("ErrorText 用 alert 語意且 big 時符合 22px 下限", async () => {
    const screen = await render(<ErrorText message="號碼不正確" size="big" />);
    const error = screen.getByRole("alert");

    expect(error.props.children).toBe("號碼不正確");
    expect(StyleSheet.flatten(error.props.style).fontSize).toBe(elder.fontMin);
  });

  it("Section 使用 24px 圓角與柔和陰影，inset 會取消陰影", async () => {
    const cardScreen = await render(
      <Section title="今日摘要">
        <Text>內容</Text>
      </Section>,
    );
    const card = cardScreen.getByText("內容").parent;
    expect(card).not.toBeNull();
    expect(StyleSheet.flatten(card!.props.style)).toMatchObject({
      borderRadius: radius.card,
      elevation: 2,
      shadowOpacity: 0.05,
    });

    const insetScreen = await render(
      <Section inset>
        <Text>綁定碼</Text>
      </Section>,
    );
    const inset = insetScreen.getByText("綁定碼").parent;
    expect(inset).not.toBeNull();
    expect(StyleSheet.flatten(inset!.props.style)).toMatchObject({
      backgroundColor: colors.background,
      borderWidth: 0,
      elevation: 0,
      shadowOpacity: 0,
    });
  });

  it("StatusPill 同時呈現圖示、底色與文字", async () => {
    const screen = await render(
      <StatusPill
        tone="critical"
        label="需要處理"
        icon={<Text testID="status-icon">!</Text>}
      />,
    );
    const pill = screen.getByText("需要處理").parent;
    expect(pill).not.toBeNull();

    expect(screen.getByTestId("status-icon")).toBeTruthy();
    expect(screen.getByText("需要處理")).toBeTruthy();
    expect(StyleSheet.flatten(pill!.props.style).backgroundColor).toBe("#FDF0F0");
  });

  it("Chip 維持至少 48dp 並揭露選取狀態與 focus", async () => {
    const screen = await render(
      <Chip label="早上" selected onPress={jest.fn()} role="checkbox" />,
    );
    const chip = screen.getByRole("checkbox");

    expect(chip.props.accessibilityState).toEqual({ selected: true });
    expect(StyleSheet.flatten(chip.props.style).minHeight).toBe(48);
    await fireEvent(chip, "focus");
    expect(StyleSheet.flatten(screen.getByRole("checkbox").props.style)).toMatchObject({
      outlineOffset: 2,
      outlineWidth: 2,
    });
  });
});
