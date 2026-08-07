import { act, fireEvent, render, waitFor } from "@testing-library/react-native";
import { Alert } from "react-native";

import EditAppointmentScreen from "@/app/guardian-detail/schedule/[scheduleId]/edit";
import { strings } from "@/lib/strings";
import type { ScheduleGroup } from "kinsun-shared/types";

const mockRouter = { back: jest.fn() };
const mockListSchedules = jest.fn();
const mockUpdateSchedule = jest.fn();
const mockDeleteSchedule = jest.fn();
const mockSignOutOn401 = jest.fn();
const mockSessionState = {
  session: { role: "guardian" as const, token: "guardian-token" },
};

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ elderId: "elder-1", scheduleId: "schedule-1" }),
  useRouter: () => mockRouter,
}));

jest.mock("@/lib/api", () => ({
  ApiError: class MockApiError extends Error {},
  listSchedules: (...args: unknown[]) => mockListSchedules(...args),
  updateSchedule: (...args: unknown[]) => mockUpdateSchedule(...args),
  deleteSchedule: (...args: unknown[]) => mockDeleteSchedule(...args),
}));

jest.mock("@/lib/SessionProvider", () => ({
  useSession: () => mockSessionState,
  useSignOutOnAuthError: () => mockSignOutOn401,
}));

const appointment: ScheduleGroup = {
  group_id: "schedule-1",
  kind: "appointment",
  title: "心臟科回診",
  created_by: "guardian",
  event_at: new Date(2026, 7, 19, 10, 30).getTime() / 1000,
  occurrences: [],
};

beforeEach(() => {
  jest.clearAllMocks();
  mockSignOutOn401.mockResolvedValue(false);
  mockListSchedules.mockResolvedValue([appointment]);
  mockUpdateSchedule.mockResolvedValue(appointment);
  mockDeleteSchedule.mockResolvedValue(undefined);
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("改回診會預填原時間，且只送現有 ScheduleInput 支援的欄位", async () => {
  const screen = await render(<EditAppointmentScreen />);

  const input = await screen.findByDisplayValue("2026-08-19 10:30");
  await fireEvent.changeText(input, "2026-08-20 14:00");
  await waitFor(() =>
    expect(screen.getByLabelText(strings.editAppointment.whenLabel).props.value).toBe(
      "2026-08-20 14:00",
    ),
  );
  await fireEvent.press(screen.getByText(strings.editAppointment.save));

  await waitFor(() =>
    expect(mockUpdateSchedule).toHaveBeenCalledWith(
      "elder-1",
      "schedule-1",
      expect.objectContaining({
        kind: "appointment",
        title: "心臟科回診",
        event_date: "2026-08-20",
        event_time: "14:00",
        occurrences: expect.any(Array),
      }),
      "guardian-token",
    ),
  );
  expect(mockUpdateSchedule.mock.calls[0][2]).not.toHaveProperty("driver");
  expect(mockUpdateSchedule.mock.calls[0][2]).not.toHaveProperty("notify_elder");
  expect(mockRouter.back).toHaveBeenCalledTimes(1);
});

test("刪除回診先確認，成功後返回上一頁", async () => {
  const alert = jest.spyOn(Alert, "alert").mockImplementation(() => undefined);
  const screen = await render(<EditAppointmentScreen />);
  await screen.findByText("心臟科回診");

  await fireEvent.press(screen.getByText(strings.editAppointment.deleteThis));
  const buttons = alert.mock.calls[0][2];
  const destructive = buttons?.find((button) => button.style === "destructive");
  await act(async () => {
    await (destructive?.onPress as (() => Promise<void>) | undefined)?.();
  });

  await waitFor(() =>
    expect(mockDeleteSchedule).toHaveBeenCalledWith(
      "elder-1",
      "schedule-1",
      "guardian-token",
    ),
  );
  expect(mockRouter.back).toHaveBeenCalledTimes(1);
});
