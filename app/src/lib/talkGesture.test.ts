import { createTalkGesture } from "./talkGesture";

describe("talkGesture 對講手勢狀態機", () => {
  test("按住說話：pressIn 開始，長按門檻到，pressOut 停止送出", () => {
    const gesture = createTalkGesture();
    expect(gesture.pressIn()).toBe("start");
    gesture.longPress();
    expect(gesture.pressOut()).toBe("stop");
  });

  test("短按一下：pressIn 開始，pressOut 維持聆聽（keep）", () => {
    const gesture = createTalkGesture();
    expect(gesture.pressIn()).toBe("start");
    expect(gesture.pressOut()).toBe("keep");
  });

  test("短按開始後再按一下：第二次 pressIn 即停止，其 pressOut 不再動作", () => {
    const gesture = createTalkGesture();
    gesture.pressIn();
    gesture.pressOut();
    expect(gesture.pressIn()).toBe("stop");
    expect(gesture.pressOut()).toBe("none");
  });

  test("短按開始後第二次按壓按很久：longPress 不會造成重覆停止", () => {
    const gesture = createTalkGesture();
    gesture.pressIn();
    gesture.pressOut();
    expect(gesture.pressIn()).toBe("stop");
    gesture.longPress();
    expect(gesture.pressOut()).toBe("none");
  });

  test("一輪結束後，下一輪按住說話照常運作", () => {
    const gesture = createTalkGesture();
    gesture.pressIn();
    gesture.longPress();
    gesture.pressOut();
    expect(gesture.pressIn()).toBe("start");
    gesture.longPress();
    expect(gesture.pressOut()).toBe("stop");
  });

  test("一輪結束後，下一輪短按切換照常運作", () => {
    const gesture = createTalkGesture();
    gesture.pressIn();
    gesture.pressOut();
    gesture.pressIn();
    gesture.pressOut();
    expect(gesture.pressIn()).toBe("start");
    expect(gesture.pressOut()).toBe("keep");
  });

  test("reset 後回到待機：pressOut 不動作，pressIn 重新開始", () => {
    const gesture = createTalkGesture();
    gesture.pressIn();
    gesture.reset();
    expect(gesture.pressOut()).toBe("none");
    expect(gesture.pressIn()).toBe("start");
  });

  test("未開始就 pressOut：不動作", () => {
    const gesture = createTalkGesture();
    expect(gesture.pressOut()).toBe("none");
  });

  test("上一輪殘留的長按旗標不影響新一輪短按", () => {
    const gesture = createTalkGesture();
    gesture.pressIn();
    gesture.longPress();
    gesture.pressOut();
    gesture.pressIn();
    expect(gesture.pressOut()).toBe("keep");
  });
});
