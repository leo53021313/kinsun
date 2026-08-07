import { fireEvent, render, waitFor, within } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import ElderHistory from "@/app/elder/history";
import { strings } from "@/lib/strings";
import { elder } from "@/lib/theme";

const mockRouter = {
  back: jest.fn(),
  canGoBack: jest.fn(),
  replace: jest.fn(),
};
const mockLoadToday = jest.fn();
let mockSessionState: {
  loading: boolean;
  session: null | { role: "elder" | "guardian"; token: string };
};

jest.mock("expo-router", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    useRouter: () => mockRouter,
    useFocusEffect: (effect: () => void | (() => void)) => React.useEffect(effect, [effect]),
  };
});

jest.mock("@/lib/SessionProvider", () => ({
  useSession: () => mockSessionState,
}));

jest.mock("@/lib/todayLog", () => ({
  loadToday: () => mockLoadToday(),
}));

jest.mock("@/components/BearStage", () => {
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  return { BearAvatar: () => <View testID="bear-avatar" /> };
});

jest.mock("phosphor-react-native/src/icons/ArrowLeft", () => ({
  ArrowLeftIcon: () => null,
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockRouter.canGoBack.mockReturnValue(true);
  mockSessionState = {
    loading: false,
    session: { role: "elder", token: "elder-token" },
  };
  mockLoadToday.mockResolvedValue([]);
});

test("顯示當天三輪真實對話，最新一輪在最上面且不出現未接線的重播按鈕", async () => {
  mockLoadToday.mockResolvedValue([
    {
      at: new Date(2026, 7, 7, 9, 5).getTime(),
      said: "第一句",
      reply: "第一個回答",
    },
    {
      at: new Date(2026, 7, 7, 15, 20).getTime(),
      said: "第二句",
      reply: "第二個回答",
    },
    {
      at: new Date(2026, 7, 7, 20, 45).getTime(),
      said: "第三句",
      reply: "第三個回答",
    },
  ]);

  const screen = await render(<ElderHistory />);
  await waitFor(() => expect(screen.getAllByTestId(/elder-history-turn-/)).toHaveLength(3));

  const cards = screen.getAllByTestId(/elder-history-turn-/);
  expect(within(cards[0]).getByText("您說：第三句")).toBeTruthy();
  expect(within(cards[0]).getByText("阿白說：第三個回答")).toBeTruthy();
  expect(within(cards[0]).getByText("晚上 8:45")).toBeTruthy();
  expect(within(cards[2]).getByText("您說：第一句")).toBeTruthy();
  expect(screen.queryByText(strings.elderHistory.replay)).toBeNull();

  const labels = screen.container.queryAll((instance) => instance.type === "Text");
  expect(labels.length).toBeGreaterThan(0);
  for (const label of labels) {
    expect(label.props.maxFontSizeMultiplier).toBeUndefined();
    expect(StyleSheet.flatten(label.props.style).fontSize).toBeGreaterThanOrEqual(elder.fontMin);
  }
});

test("空紀錄顯示當天空狀態，頁首固定在內容捲動層外", async () => {
  const screen = await render(<ElderHistory />);
  await waitFor(() => expect(screen.getByText(strings.elderHistory.empty)).toBeTruthy());

  const scrollContent = screen.getByTestId("elder-history-content");
  expect(within(scrollContent).queryByTestId("elder-history-header")).toBeNull();
  expect(screen.getByTestId("bear-avatar")).toBeTruthy();
});

test("返回鍵優先回上一頁，沒有返回堆疊時直接回對講機", async () => {
  const screen = await render(<ElderHistory />);
  await waitFor(() => expect(screen.getByText(strings.elderHistory.empty)).toBeTruthy());

  await fireEvent.press(screen.getByTestId("elder-history-back"));
  expect(mockRouter.back).toHaveBeenCalledTimes(1);
  expect(mockRouter.replace).not.toHaveBeenCalled();

  mockRouter.canGoBack.mockReturnValue(false);
  await fireEvent.press(screen.getByTestId("elder-history-back"));
  expect(mockRouter.replace).toHaveBeenCalledWith("/elder/talk");
});

test("非長輩 session 不讀取本機逐字紀錄並導回身分頁", async () => {
  mockSessionState = {
    loading: false,
    session: { role: "guardian", token: "guardian-token" },
  };

  await render(<ElderHistory />);
  await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith("/role"));
  expect(mockLoadToday).not.toHaveBeenCalled();
});
