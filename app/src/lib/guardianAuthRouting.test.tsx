import { fireEvent, render, waitFor } from "@testing-library/react-native";

import GuardianLogin from "@/app/auth/guardian-login";
import GuardianRegister from "@/app/auth/guardian-register";
import { strings } from "@/lib/strings";

const mockRouter = { replace: jest.fn() };
const mockLoginGuardian = jest.fn();
const mockRegisterGuardian = jest.fn();
const mockSignIn = jest.fn();
const mockSessionState: {
  session: null | { role: "guardian" | "elder"; token: string; display_name: string };
} = { session: null };

jest.mock("expo-router", () => ({
  Link: ({ children }: { children: React.ReactNode }) => children,
  useRouter: () => mockRouter,
}));

jest.mock("@/lib/api", () => ({
  ApiError: class MockApiError extends Error {
    status = 0;
  },
  loginGuardian: (...args: unknown[]) => mockLoginGuardian(...args),
  registerGuardian: (...args: unknown[]) => mockRegisterGuardian(...args),
}));

jest.mock("@/lib/SessionProvider", () => ({
  useSession: () => ({ ...mockSessionState, signIn: mockSignIn }),
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockSessionState.session = null;
  mockSignIn.mockResolvedValue(undefined);
});

test("家屬登入要等 SessionProvider 實際更新後才進 Tabs", async () => {
  mockLoginGuardian.mockResolvedValue({ token: "guardian-token", name: "家屬" });
  const screen = await render(<GuardianLogin />);

  await fireEvent.changeText(screen.getByLabelText("Email"), "guardian@example.com");
  await fireEvent.changeText(screen.getByLabelText(strings.common.passwordLabel), "password-8");
  await fireEvent.press(screen.getByText(strings.common.login));

  await waitFor(() =>
    expect(mockSignIn).toHaveBeenCalledWith({
      role: "guardian",
      token: "guardian-token",
      display_name: "家屬",
    }),
  );
  expect(mockRouter.replace).not.toHaveBeenCalled();

  mockSessionState.session = {
    role: "guardian",
    token: "guardian-token",
    display_name: "家屬",
  };
  await screen.rerender(<GuardianLogin />);

  await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith("/guardian/home"));
});

test("家屬註冊同樣要等 session 更新，避免 Tabs 守門讀到 null", async () => {
  mockRegisterGuardian.mockResolvedValue({ token: "guardian-token", name: "女兒" });
  const screen = await render(<GuardianRegister />);

  await fireEvent.changeText(screen.getByLabelText(strings.guardianRegister.nameLabel), "女兒");
  await fireEvent.changeText(screen.getByLabelText("Email"), "daughter@example.com");
  await fireEvent.changeText(screen.getByLabelText(strings.common.passwordLabel), "password-8");
  await fireEvent.press(screen.getByText(strings.guardianRegister.submit));

  await waitFor(() =>
    expect(mockSignIn).toHaveBeenCalledWith({
      role: "guardian",
      token: "guardian-token",
      display_name: "女兒",
    }),
  );
  expect(mockRouter.replace).not.toHaveBeenCalled();

  mockSessionState.session = {
    role: "guardian",
    token: "guardian-token",
    display_name: "女兒",
  };
  await screen.rerender(<GuardianRegister />);

  await waitFor(() => expect(mockRouter.replace).toHaveBeenCalledWith("/guardian/home"));
});
