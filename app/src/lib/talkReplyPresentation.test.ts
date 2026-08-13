import {
  applyReplyContentFrame,
  collapsedReplySummary,
  firstReplyAudioText,
  hasPlayableReplyAudio,
  shouldScrollTalkContent,
} from "./talkReplyPresentation";

test("reply 已帶完整回答，續段只更新完成旗標、不重複後半段", () => {
  const first = applyReplyContentFrame(
    { reply: "", finalReceived: false },
    {
      type: "reply",
      text: "膝蓋痠先坐下休息。連著幾天就跟醫師說。",
      chunk_count: 2,
    },
  );
  expect(first).toEqual({
    reply: "膝蓋痠先坐下休息。連著幾天就跟醫師說。",
    finalReceived: false,
  });
  expect(
    applyReplyContentFrame(first, {
      type: "chunk",
      text: "連著幾天就跟醫師說。",
      is_last: true,
    }),
  ).toEqual({
    reply: "膝蓋痠先坐下休息。連著幾天就跟醫師說。",
    finalReceived: true,
  });
  expect(firstReplyAudioText(first.reply, 2)).toBe("膝蓋痠先坐下休息。");
  expect(firstReplyAudioText("好喔。請您先坐下休息。再看看。", 3)).toBe(
    "好喔。請您先坐下休息。",
  );
});

test("收合摘要固定取前 12 字再加省略號", () => {
  expect(collapsedReplySummary("剛才阿白說：", "一二三四五六七八九十十一十二十三"))
    .toBe("剛才阿白說：一二三四五六七八九十十一…");
});

test("只有系統字級達 150% 才讓內容層捲動", () => {
  expect(shouldScrollTalkContent(1.49)).toBe(false);
  expect(shouldScrollTalkContent(1.5)).toBe(true);
  expect(shouldScrollTalkContent(2)).toBe(true);
});

test("空白終止訊框只收尾、不送進播放器", () => {
  expect(
    hasPlayableReplyAudio({ type: "chunk", text: "", audio_url: "file:///empty.m4a" }),
  ).toBe(false);
  expect(
    hasPlayableReplyAudio({
      type: "chunk",
      text: "第二段回答。",
      audio_url: "file:///chunk.m4a",
    }),
  ).toBe(true);
});
