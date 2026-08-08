import { render } from "@testing-library/react-native";

import RootLayout from "@/app/_layout";
import { elder } from "@/lib/theme";

type CapturedScreen = {
  name: string;
  options?: {
    title?: string;
    headerShown?: boolean;
    headerTitleStyle?: { fontSize?: number };
  };
};

jest.mock("expo-router", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  const Stack = Object.assign(
    ({ children }: { children?: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    {
      Screen: (props: CapturedScreen) =>
        React.createElement(View, {
          accessibilityLabel: props.options?.title,
          accessibilityHint: String(props.options?.headerTitleStyle?.fontSize ?? ""),
          testID: `root-stack-${props.name}`,
        }),
    },
  );
  return { Stack };
});

jest.mock("@/lib/SessionProvider", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    SessionProvider: ({ children }: { children?: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
  };
});

test("長輩提醒頁使用核定標題，不顯示檔案路由名稱", async () => {
  const screen = await render(<RootLayout />);

  expect(screen.getByTestId("root-stack-elder/notifications").props.accessibilityLabel).toBe(
    "阿白的提醒",
  );
});

test.each(["elder/bind", "elder/login", "elder/notifications"])(
  "%s 的原生 header 標題不低於長輩端 22px 下限",
  async (route) => {
    // 規則 1「文字下限 22px」管的是長輩看得到的**每一段**文字，原生 header 的標題
    // 也算。全域 screenOptions 只設了 fontWeight，字級會落在系統預設（約 17px）
    // ——比長輩端畫面內任何一個字都小，而且用眼睛看很容易略過。
    //
    // 家屬端刻意不驗：那一端沒有這條下限，把它一起放大反而是錯的。
    const screen = await render(<RootLayout />);

    expect(screen.getByTestId(`root-stack-${route}`).props.accessibilityHint).toBe(
      String(elder.fontMin),
    );
  },
);
