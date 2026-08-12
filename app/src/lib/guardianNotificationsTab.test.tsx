import { render, waitFor } from "@testing-library/react-native";

import GuardianNotifications from "@/app/guardian/notifications";

const mockRouter = { replace: jest.fn() };
const mockNavigation = { setOptions: jest.fn() };
const mockListNotifications = jest.fn();
const mockLoadSeenAt = jest.fn();
const mockSaveSeenAt = jest.fn();
const mockSignOutOn401 = jest.fn();
let mockPathname = "/guardian/home";
const mockSessionState = {
  loading: false,
  session: { role: "guardian" as const, token: "guardian-token" },
};

jest.mock("expo-router", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    useRouter: () => mockRouter,
    useNavigation: () => mockNavigation,
    usePathname: () => mockPathname,
    useFocusEffect: (effect: () => void | (() => void)) =>
      React.useEffect(() => {
        if (mockPathname === "/guardian/notifications") return effect();
      }, [effect]),
  };
});

jest.mock("@/lib/api", () => ({
  listNotifications: (...args: unknown[]) => mockListNotifications(...args),
}));

jest.mock("@/lib/notificationsSeen", () => ({
  loadSeenAt: (...args: unknown[]) => mockLoadSeenAt(...args),
  saveSeenAt: (...args: unknown[]) => mockSaveSeenAt(...args),
}));

jest.mock("@/lib/SessionProvider", () => ({
  useSession: () => mockSessionState,
  useSignOutOnAuthError: () => mockSignOutOn401,
}));

jest.mock("kinsun-shared/format", () => ({
  formatTime: (timestamp: number) => String(timestamp),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockPathname = "/guardian/home";
  mockSignOutOn401.mockResolvedValue(false);
  mockLoadSeenAt.mockResolvedValue(15);
  mockSaveSeenAt.mockResolvedValue(undefined);
});

test("通知頁在背景預載時自行計算並設定 tab 未讀徽章", async () => {
  mockListNotifications.mockResolvedValue([
    { content: "已讀", created_at: 10 },
    { content: "未讀一", created_at: 20 },
    { content: "未讀二", created_at: 30 },
  ]);

  await render(<GuardianNotifications />);

  await waitFor(() => expect(mockNavigation.setOptions).toHaveBeenCalledWith({ tabBarBadge: 2 }));
  expect(mockLoadSeenAt).toHaveBeenCalledWith();
  expect(mockSaveSeenAt).not.toHaveBeenCalled();
});

test("進入通知 tab 後以最大 created_at 更新水位並清除徽章", async () => {
  mockPathname = "/guardian/notifications";
  mockListNotifications.mockResolvedValue([
    { content: "較新", created_at: 50 },
    { content: "較舊", created_at: 20 },
    { content: "中間", created_at: 35 },
  ]);

  await render(<GuardianNotifications />);

  await waitFor(() => expect(mockSaveSeenAt).toHaveBeenCalledWith(50));
  expect(mockNavigation.setOptions).toHaveBeenCalledWith({ tabBarBadge: undefined });
  expect(mockLoadSeenAt).not.toHaveBeenCalled();
});
