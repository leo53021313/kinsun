import { render, waitFor } from "@testing-library/react-native";
import { BackHandler } from "react-native";

import GuardianTabsLayout from "@/app/guardian/_layout";

type CapturedScreen = {
  name: string;
  listeners?: { tabPress?: (event: { preventDefault: () => void }) => void };
  options?: { title?: string; lazy?: boolean };
};

const mockRouter = {
  navigate: jest.fn(),
  push: jest.fn(),
};
const mockRefreshPrimaryElder = jest.fn();
const mockScreens: CapturedScreen[] = [];
let mockPathname = "/guardian/home";
let mockBackHandler: (() => boolean | null | undefined) | undefined;
let mockSessionState: {
  loading: boolean;
  session: null | { role: "elder" | "guardian"; token: string };
};
let mockGuardianState: {
  primaryElder: null | { elder_id: string; name: string; nickname: string };
  loaded: boolean;
  error: string;
  refreshPrimaryElder: typeof mockRefreshPrimaryElder;
};

jest.mock("expo-router", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  const Tabs = Object.assign(
    ({ children }: { children?: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    {
      Screen: (props: CapturedScreen) => {
        mockScreens.push(props);
        return null;
      },
    },
  );
  return {
    Tabs,
    Redirect: ({ href }: { href: string }) =>
      React.createElement(View, { testID: "guardian-tabs-redirect", accessibilityLabel: href }),
    useRouter: () => mockRouter,
    usePathname: () => mockPathname,
    useFocusEffect: (effect: () => void | (() => void)) => React.useEffect(effect, [effect]),
  };
});

jest.mock("@/lib/SessionProvider", () => ({
  useSession: () => mockSessionState,
}));

jest.mock("@/lib/GuardianTabsProvider", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    GuardianTabsProvider: ({ children }: { children?: React.ReactNode }) =>
      React.createElement(React.Fragment, null, children),
    useGuardianTabsState: () => mockGuardianState,
  };
});

jest.mock("phosphor-react-native/src/icons/Bell", () => ({ BellIcon: () => null }));
jest.mock("phosphor-react-native/src/icons/ChartDonut", () => ({ ChartDonutIcon: () => null }));
jest.mock("phosphor-react-native/src/icons/House", () => ({ HouseIcon: () => null }));
jest.mock("phosphor-react-native/src/icons/Plus", () => ({ PlusIcon: () => null }));
jest.mock("phosphor-react-native/src/icons/UserCircle", () => ({ UserCircleIcon: () => null }));

beforeEach(() => {
  jest.clearAllMocks();
  mockScreens.length = 0;
  mockPathname = "/guardian/home";
  mockBackHandler = undefined;
  mockSessionState = {
    loading: false,
    session: { role: "guardian", token: "guardian-token" },
  };
  mockGuardianState = {
    primaryElder: { elder_id: "elder-1", name: "王大明", nickname: "阿公" },
    loaded: true,
    error: "",
    refreshPrimaryElder: mockRefreshPrimaryElder,
  };
  jest.spyOn(BackHandler, "addEventListener").mockImplementation((_eventName, handler) => {
    mockBackHandler = handler;
    return { remove: jest.fn() };
  });
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("家屬端只註冊五個底部項目，通知頁預載且個人頁顯示目前長輩稱呼", async () => {
  await render(<GuardianTabsLayout />);

  expect(mockScreens.map((screen) => screen.name)).toEqual([
    "home",
    "report",
    "add",
    "notifications",
    "profile",
  ]);
  expect(mockScreens.find((screen) => screen.name === "notifications")?.options?.lazy).toBe(false);
  expect(mockScreens.find((screen) => screen.name === "profile")?.options?.title).toBe("阿公");
});

test("中央新增鍵攔截 tab 切換，重讀第一位長輩後 push 到外層行程頁", async () => {
  mockRefreshPrimaryElder.mockResolvedValue({
    elder: { elder_id: "elder-1", name: "王大明", nickname: "阿公" },
    error: null,
  });
  await render(<GuardianTabsLayout />);
  const addScreen = mockScreens.find((screen) => screen.name === "add");
  const preventDefault = jest.fn();

  addScreen?.listeners?.tabPress?.({ preventDefault });

  expect(preventDefault).toHaveBeenCalledTimes(1);
  await waitFor(() =>
    expect(mockRouter.push).toHaveBeenCalledWith({
      pathname: "/guardian-detail/elder/[elderId]/schedules",
      params: { elderId: "elder-1" },
    }),
  );
});

test("沒有長輩時中央新增鍵回首頁，不會進入不存在對象的深層頁", async () => {
  mockRefreshPrimaryElder.mockResolvedValue({ elder: null, error: null });
  await render(<GuardianTabsLayout />);
  const addScreen = mockScreens.find((screen) => screen.name === "add");

  addScreen?.listeners?.tabPress?.({ preventDefault: jest.fn() });

  await waitFor(() => expect(mockRouter.navigate).toHaveBeenCalledWith("/guardian/home"));
  expect(mockRouter.push).not.toHaveBeenCalled();
});

test("Android 返回鍵在非首頁 tab 先回首頁，在首頁才交還系統退出", async () => {
  mockPathname = "/guardian/notifications";
  const firstRender = await render(<GuardianTabsLayout />);
  expect(mockBackHandler?.()).toBe(true);
  expect(mockRouter.navigate).toHaveBeenCalledWith("/guardian/home");

  await firstRender.unmount();
  jest.clearAllMocks();
  mockPathname = "/guardian/home";
  await render(<GuardianTabsLayout />);
  expect(mockBackHandler?.()).toBe(false);
  expect(mockRouter.navigate).not.toHaveBeenCalled();
});

test("未登入或身分不符時直接導回身分頁，不渲染 tab bar", async () => {
  mockSessionState = { loading: false, session: null };
  const screen = await render(<GuardianTabsLayout />);

  expect(screen.getByTestId("guardian-tabs-redirect").props.accessibilityLabel).toBe("/role");
  expect(mockScreens).toHaveLength(0);
  expect(BackHandler.addEventListener).not.toHaveBeenCalled();
});
