import { fireEvent, render, waitFor } from "@testing-library/react-native";

import SchedulesManage from "@/app/guardian-detail/elder/[elderId]/schedules";
import { strings } from "@/lib/strings";

const mockRouter = { push: jest.fn() };
const mockListSchedules = jest.fn();
const mockSignOutOn401 = jest.fn();
const mockSessionState = {
  session: { role: "guardian" as const, token: "guardian-token" },
};

jest.mock("expo-router", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    useLocalSearchParams: () => ({ elderId: "elder-1" }),
    useRouter: () => mockRouter,
    useFocusEffect: (effect: () => void | (() => void)) => React.useEffect(effect, [effect]),
  };
});

jest.mock("@/lib/api", () => ({
  ApiError: class MockApiError extends Error {},
  createSchedule: jest.fn(),
  deleteSchedule: jest.fn(),
  updateSchedule: jest.fn(),
  listSchedules: (...args: unknown[]) => mockListSchedules(...args),
}));

jest.mock("@/lib/SessionProvider", () => ({
  useSession: () => mockSessionState,
  useSignOutOnAuthError: () => mockSignOutOn401,
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockSignOutOn401.mockResolvedValue(false);
  mockListSchedules.mockResolvedValue([
    {
      group_id: "schedule-1",
      kind: "appointment",
      title: "心臟科回診",
      created_by: "guardian",
      event_at: new Date(2026, 7, 19, 10, 30).getTime() / 1000,
      occurrences: [],
    },
  ]);
});

test("行程清單的回診編輯會 push 到 Tabs 外的獨立頁", async () => {
  const screen = await render(<SchedulesManage />);
  await waitFor(() => expect(screen.getByText(/心臟科回診/)).toBeTruthy());

  await fireEvent.press(screen.getByText(strings.common.edit));

  expect(mockRouter.push).toHaveBeenCalledWith({
    pathname: "/guardian-detail/schedule/[scheduleId]/edit",
    params: { scheduleId: "schedule-1", elderId: "elder-1" },
  });
});
