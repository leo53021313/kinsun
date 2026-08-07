import { render } from "@testing-library/react-native";

import CriticalAlertDetailScreen from "@/app/guardian-detail/alert/[eventId]";
import { strings } from "@/lib/strings";

jest.mock("phosphor-react-native/src/icons/WarningCircle", () => ({
  WarningCircleIcon: () => null,
}));

test("危急詳情在後端與重新同意完成前只顯示安全降級內容", async () => {
  const screen = await render(<CriticalAlertDetailScreen />);

  expect(screen.getByText(strings.criticalAlert.safeFallbackTitle)).toBeTruthy();
  expect(screen.getByText(strings.criticalAlert.reasonUnavailable)).toBeTruthy();
  expect(screen.getByText(strings.criticalAlert.timeUnavailable)).toBeTruthy();
  expect(screen.queryByText(strings.criticalAlert.recordingSection)).toBeNull();
  expect(screen.queryByText(strings.criticalAlert.transcriptSection)).toBeNull();
  expect(screen.queryByText(strings.criticalAlert.callElder)).toBeNull();
});
