import { fireEvent, render, waitFor } from "@testing-library/react-native";
import { Pressable, Text } from "react-native";

import {
  GuardianTabsProvider,
  useGuardianTabsState,
} from "@/lib/GuardianTabsProvider";

const mockListElders = jest.fn();
const mockSignOutOn401 = jest.fn();
const mockSessionState = {
  loading: false,
  session: { role: "guardian" as const, token: "guardian-token" },
};

jest.mock("@/lib/api", () => ({
  listElders: (...args: unknown[]) => mockListElders(...args),
}));

jest.mock("@/lib/SessionProvider", () => ({
  useSession: () => mockSessionState,
  useSignOutOnAuthError: () => mockSignOutOn401,
}));

function StateProbe() {
  const { primaryElder, loaded, error, refreshPrimaryElder } = useGuardianTabsState();
  return (
    <>
      <Text testID="primary-elder">{primaryElder?.elder_id ?? "none"}</Text>
      <Text testID="primary-loaded">{loaded ? "loaded" : "loading"}</Text>
      <Text testID="primary-error">{error}</Text>
      <Pressable testID="primary-refresh" onPress={() => void refreshPrimaryElder()} />
    </>
  );
}

beforeEach(() => {
  jest.clearAllMocks();
  mockListElders.mockReset();
  mockSignOutOn401.mockReset();
  mockSignOutOn401.mockResolvedValue(false);
});

test("暫用目前長輩規則固定取 listElders 第一位，不依畫面推測其他欄位", async () => {
  mockListElders.mockResolvedValue([
    { elder_id: "elder-first", name: "王大明", nickname: "阿公" },
    { elder_id: "elder-second", name: "林美麗", nickname: "阿嬤" },
  ]);
  const screen = await render(
    <GuardianTabsProvider>
      <StateProbe />
    </GuardianTabsProvider>,
  );

  await waitFor(() => expect(screen.getByTestId("primary-elder").props.children).toBe("elder-first"));
  expect(screen.getByTestId("primary-loaded").props.children).toBe("loaded");
  expect(mockListElders).toHaveBeenCalledWith("guardian-token");
});

test("手動重新整理會重新套用後端當下的第一位長輩", async () => {
  mockListElders
    .mockResolvedValueOnce([{ elder_id: "elder-old", name: "舊資料", nickname: "" }])
    .mockResolvedValueOnce([{ elder_id: "elder-new", name: "新資料", nickname: "" }]);
  const screen = await render(
    <GuardianTabsProvider>
      <StateProbe />
    </GuardianTabsProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("primary-elder").props.children).toBe("elder-old"));

  await fireEvent.press(screen.getByTestId("primary-refresh"));

  await waitFor(() => expect(screen.getByTestId("primary-elder").props.children).toBe("elder-new"));
  expect(mockListElders).toHaveBeenCalledTimes(2);
});
