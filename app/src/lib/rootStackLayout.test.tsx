import { render } from "@testing-library/react-native";

import RootLayout from "@/app/_layout";

type CapturedScreen = {
  name: string;
  options?: { title?: string; headerShown?: boolean };
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
