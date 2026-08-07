import { render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import {
  BearStage,
  bearSpeechCue,
  sanitizeEmotion,
} from "@/components/BearStage";
import { avatar, talkState } from "@/lib/theme";

jest.mock("@/components/OttoBearRenderer", () => ({
  OttoBearRenderer: () => null,
}));

describe("BearStage", () => {
  it("舞台固定在 top 140 且維持 209 × 300", async () => {
    const screen = await render(<BearStage systemState="listening" />);
    expect(StyleSheet.flatten(screen.getByTestId("bear-stage").props.style)).toMatchObject({
      position: "absolute",
      top: avatar.stageTop,
      width: avatar.stageW,
      height: avatar.stageH,
      zIndex: 1,
    });
  });

  it("光暈只跟系統態走", async () => {
    const screen = await render(
      <BearStage systemState="speaking" emotion="celebrating" />,
    );
    expect(StyleSheet.flatten(screen.getByTestId("bear-stage-glow").props.style)).toMatchObject({
      backgroundColor: talkState.speaking.glow,
    });
  });
});

test("情緒黑名單在角色元件最後一關仍會擋掉", () => {
  expect(sanitizeEmotion("angry")).toBeNull();
  expect(sanitizeEmotion("scared")).toBeNull();
  expect(sanitizeEmotion("celebrating")).toBe("celebrating");
});

test("回應情緒只在 speaking 態送進 Otto", () => {
  const cue = { key: "1", text: "慢慢來", durationMs: 1200 };
  expect(bearSpeechCue("speaking", "touched", cue)).toEqual({
    ...cue,
    emotion: "touched",
  });
  expect(bearSpeechCue("idle", "touched", cue)).toBe(cue);
});
