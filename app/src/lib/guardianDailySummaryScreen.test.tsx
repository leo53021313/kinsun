import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Share } from "react-native";

import DailySummaryScreen from "@/app/guardian-detail/elder/[elderId]/summary";
import { strings } from "@/lib/strings";

const mockListDailySummaries = jest.fn();
const mockSignOutOn401 = jest.fn();
const mockSessionState = {
  session: { role: "guardian" as const, token: "guardian-token" },
};

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ elderId: "elder-1" }),
}));

jest.mock("@/lib/api", () => ({
  listDailySummaries: (...args: unknown[]) => mockListDailySummaries(...args),
}));

jest.mock("@/lib/SessionProvider", () => ({
  useSession: () => mockSessionState,
  useSignOutOnAuthError: () => mockSignOutOn401,
}));

jest.mock("phosphor-react-native/src/icons/CaretLeft", () => ({ CaretLeftIcon: () => null }));
jest.mock("phosphor-react-native/src/icons/CaretRight", () => ({ CaretRightIcon: () => null }));

beforeEach(() => {
  jest.clearAllMocks();
  mockSignOutOn401.mockResolvedValue(false);
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("每日摘要由新到舊切換、鎖住邊界並呼叫系統分享", async () => {
  mockListDailySummaries.mockResolvedValue([
    { date: "2026-08-06", content: "最新摘要", created_at: 20 },
    { date: "2026-08-05", content: "較舊摘要", created_at: 10 },
  ]);
  const share = jest.spyOn(Share, "share").mockResolvedValue({ action: Share.sharedAction });
  const screen = await render(<DailySummaryScreen />);

  await waitFor(() => expect(screen.getByText("最新摘要")).toBeTruthy());
  expect(screen.getByLabelText(strings.dailySummary.nextDay).props.accessibilityState).toEqual({
    disabled: true,
  });

  await fireEvent.press(screen.getByLabelText(strings.dailySummary.prevDay));
  await waitFor(() => expect(screen.getByText("較舊摘要")).toBeTruthy());
  expect(screen.getByLabelText(strings.dailySummary.prevDay).props.accessibilityState).toEqual({
    disabled: true,
  });

  await fireEvent.press(screen.getByLabelText(strings.dailySummary.nextDay));
  await waitFor(() => expect(screen.getByText("最新摘要")).toBeTruthy());
  await fireEvent.press(screen.getByText(strings.dailySummary.share));

  await waitFor(() =>
    expect(share).toHaveBeenCalledWith({
      message: "2026-08-06 的摘要\n\n最新摘要\n\n（由金孫產生）",
    }),
  );
});

test("摘要載入失敗時顯示錯誤，不會誤顯示成空資料", async () => {
  mockListDailySummaries.mockRejectedValue(new Error("offline"));
  const screen = await render(<DailySummaryScreen />);

  await waitFor(() => expect(screen.getByText(strings.common.loadFailed)).toBeTruthy());
  expect(screen.queryByText(strings.elderDetail.noSummaries)).toBeNull();
});
