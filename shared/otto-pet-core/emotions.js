// emotions.js — 50 種情緒定義：臉部參數 + 身體動作剪輯 + 特效
// clip 通道皆為「相對量」：sx/sy 是相對 1 的增減、rootY 負值向上、headRot 由 pet.js 軟上限收斂
(function () {
  const PET = (window.PET = window.PET || {});

  const F = PET.defaultFace;
  function face(over) { return Object.assign(F(), over); }

  // ---------- 動作原型 ----------
  // 每個原型吃一個 0.5~1.5 的力度 a，回傳 Clip frames；情緒只要挑原型+調力度，
  // 需要獨特動作的再自己寫 frames。
  const MOTION = {
    // 原地彈跳 n 下
    hop: (a = 1, n = 2) => {
      const fr = [{ t: 0, ch: {} }];
      let t = 0;
      for (let i = 0; i < n; i++) {
        fr.push({ t: (t += 0.2), ch: { rootY: -34 * a, sy: 0.05 * a, sx: -0.04 * a } });
        fr.push({ t: (t += 0.2), ch: { rootY: 0, sy: -0.05 * a, sx: 0.05 * a } });
      }
      fr.push({ t: t + 0.35, ch: {} });
      return fr;
    },
    // 左右搖擺 n 個來回
    sway: (a = 1, n = 2, dur = 0.55) => {
      const fr = [{ t: 0, ch: {} }];
      for (let i = 0; i < n * 2; i++)
        fr.push({ t: dur * (i + 1), ch: { rootRot: (i % 2 ? -1 : 1) * 2.6 * a } });
      fr.push({ t: dur * (n * 2 + 1), ch: {} });
      return fr;
    },
    // 縮起來（害怕/內向）：下沉、變窄、往一側靠
    shrink: (a = 1, side = -1, hold = 2.6) => [
      { t: 0, ch: {} },
      { t: 0.25, ch: { rootY: 8 * a, sy: -0.05 * a, sx: 0.03 * a, rootX: 14 * a * side, rootRot: 3 * a * side } },
      { t: hold, ch: { rootY: 8 * a, sy: -0.05 * a, sx: 0.03 * a, rootX: 14 * a * side, rootRot: 3 * a * side } },
      { t: hold + 0.5, ch: {} },
    ],
    // 挺起來（得意/勇敢）：長高、胸口前挺
    puff: (a = 1, hold = 2.4) => [
      { t: 0, ch: {} },
      { t: 0.3, ch: { rootY: -14 * a, sy: 0.06 * a, sx: -0.02 * a } },
      { t: 0.55, ch: { rootY: -10 * a, sy: 0.05 * a, sx: 0.04 * a } },
      { t: hold, ch: { rootY: -10 * a, sy: 0.05 * a, sx: 0.04 * a } },
      { t: hold + 0.55, ch: {} },
    ],
    // 垂下去（難過/失望）：低頭、下沉
    droop: (a = 1, hold = 3.4) => [
      { t: 0, ch: {} },
      { t: 0.7, ch: { headRot: -4 * a, headY: 15 * a, sy: -0.035 * a, rootY: 6 * a } },
      { t: hold, ch: { headRot: -4 * a, headY: 15 * a, sy: -0.035 * a, rootY: 6 * a } },
      { t: hold + 0.7, ch: { headRot: -3 * a, headY: 12 * a } },
    ],
    // 歪頭定住（疑惑/好奇）
    tilt: (a = 1, hold = 2.6) => [
      { t: 0, ch: {} },
      { t: 0.5, ch: { headRot: 6.5 * a, headY: 4 * a } },
      { t: hold, ch: { headRot: 6.5 * a, headY: 4 * a } },
      { t: hold + 0.5, ch: { headRot: 5.5 * a, headY: 3 * a } },
    ],
    // 左右快速抖（生氣/緊張）
    jitter: (a = 1, hold = 2.2) => [
      { t: 0, ch: {} },
      { t: 0.1, ch: { rootX: -10 * a } },
      { t: 0.2, ch: { rootX: 10 * a } },
      { t: 0.3, ch: { rootX: -8 * a } },
      { t: 0.4, ch: { rootX: 8 * a } },
      { t: 0.5, ch: { rootX: 0 } },
      { t: 0.75, ch: { sx: 0.06 * a, sy: 0.035 * a, rootY: -6 * a } },
      { t: hold, ch: { sx: 0.06 * a, sy: 0.035 * a, rootY: -6 * a } },
      { t: hold + 0.5, ch: {} },
    ],
    // 點頭（同意/道歉）
    nod: (a = 1, n = 2) => {
      const fr = [{ t: 0, ch: {} }];
      let t = 0;
      for (let i = 0; i < n; i++) {
        fr.push({ t: (t += 0.32), ch: { headY: 20 * a, headRot: -2 * a, rootY: 5 * a } });
        fr.push({ t: (t += 0.32), ch: { headY: 0, rootY: 0 } });
      }
      fr.push({ t: t + 0.4, ch: {} });
      return fr;
    },
    // 大笑：後仰 + 抖
    guffaw: (a = 1) => [
      { t: 0, ch: {} },
      { t: 0.2, ch: { headRot: -3 * a, headY: -10 * a, sy: 0.05 * a, rootY: -12 * a } },
      { t: 0.45, ch: { headY: 6 * a, sy: -0.04 * a, rootY: 4 * a } },
      { t: 0.7, ch: { headRot: -3 * a, headY: -10 * a, sy: 0.05 * a, rootY: -12 * a } },
      { t: 0.95, ch: { headY: 6 * a, sy: -0.04 * a, rootY: 4 * a } },
      { t: 1.2, ch: { headRot: -2 * a, headY: -6 * a, sy: 0.03 * a } },
      { t: 1.7, ch: {} },
    ],
    // 靜止（平靜/放鬆）
    still: (dur = 0.7) => [{ t: 0, ch: {} }, { t: dur, ch: {} }],
  };

  // 情緒宣告糖：{ zh, emoji, face, clip:frames, fx, tremble, loop, linger, fxLoop }
  function E(def) {
    const opts = {};
    if (def.fx) opts.fx = def.fx;
    if (def.tremble) opts.tremble = def.tremble;
    if (def.loop) opts.loop = true;
    return {
      zh: def.zh, emoji: def.emoji, group: def.group || "其他",
      face: face(def.face || {}),
      clip: new PET.Clip(def.clip || MOTION.still(), opts),
      linger: def.linger || {},
      fxLoop: def.fxLoop || null,
    };
  }

  PET.EMOTIONS = {
    // ============ 正向 · 高能量 ============
    happy: E({
      zh: "開心", emoji: "😊", group: "正向",
      face: { eyeOpen: 0.1, eyeArc: 1, mCurve: 1, mWide: 0.55, mOpen: 0, blush: 1.05 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.22, ch: { rootY: -34, sy: 0.05, sx: -0.04 } },
        { t: 0.42, ch: { rootY: 0, sy: -0.05, sx: 0.05 } },
        { t: 0.62, ch: { rootY: -22, sy: 0.04, sx: -0.03 } },
        { t: 0.82, ch: { rootY: 0 } },
        { t: 1.35, ch: { rootRot: 2.2 } },
        { t: 1.9, ch: { rootRot: -2.2 } },
        { t: 2.45, ch: {} },
      ],
      fx: [{ t: 0.15, type: "heart", x: 1000, y: 300 }],
      linger: { rootRotSwayAmp: 1.6, rootRotSwayHz: 0.55 },
    }),

    excited: E({
      zh: "興奮", emoji: "🤩", group: "正向",
      face: { eyeOpen: 1.2, pupilScale: 1.22, mOpen: 0.75, mWide: 0.8, mCurve: 0.9, blush: 1.1 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.16, ch: { rootY: -52, sy: 0.07, sx: -0.05 } },
        { t: 0.32, ch: { rootY: 0, sy: -0.07, sx: 0.07 } },
        { t: 0.48, ch: { rootY: -52, sy: 0.07, sx: -0.05, rootRot: 3 } },
        { t: 0.64, ch: { rootY: 0, sy: -0.07, sx: 0.07 } },
        { t: 0.8, ch: { rootY: -44, sy: 0.06, rootRot: -3 } },
        { t: 0.98, ch: { rootY: 0 } },
        { t: 1.2, ch: {} },
      ],
      fx: [
        { t: 0.1, type: "sparkle", x: 560, y: 260 },
        { t: 0.3, type: "sparkle", x: 1010, y: 210 },
        { t: 0.55, type: "sparkle", x: 900, y: 130 },
      ],
      linger: { rootYBounceAmp: 8, rootYBounceHz: 2.2 },
    }),

    laughing: E({
      zh: "大笑", emoji: "😂", group: "正向",
      face: { eyeOpen: 0.06, eyeArc: 1, mOpen: 0.85, mWide: 0.95, mCurve: 0.9, mRound: 0.1, blush: 1.25, tear: 0.35 },
      clip: MOTION.guffaw(1),
      fx: [
        { t: 0.2, type: "sparkle", x: 1010, y: 220, s1: 1.2 },
        { t: 0.5, type: "drop", x: 620, y: 400, vy: 30, vx: -14, gravity: 70, life: 0.9 },
        { t: 0.95, type: "drop", x: 925, y: 400, vy: 30, vx: 14, gravity: 70, life: 0.9 },
      ],
      linger: { rootYBounceAmp: 5, rootYBounceHz: 3.1 },
    }),


    celebrating: E({
      zh: "慶祝", emoji: "🎉", group: "正向",
      face: { eyeOpen: 0.08, eyeArc: 1, mOpen: 0.7, mWide: 0.9, mCurve: 1, blush: 1.2 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.18, ch: { rootY: -58, sy: 0.08, sx: -0.06, rootRot: 3 } },
        { t: 0.4, ch: { rootY: 0, sy: -0.06, sx: 0.06, rootRot: -3 } },
        { t: 0.6, ch: { rootY: -46, sy: 0.06, rootRot: 3 } },
        { t: 0.85, ch: { rootY: 0, rootRot: 0 } },
        { t: 1.3, ch: {} },
      ],
      fx: [
        { t: 0.05, type: "sparkle", x: 540, y: 200, s1: 1.6 },
        { t: 0.2, type: "note", x: 1020, y: 180, s1: 1.4 },
        { t: 0.4, type: "sparkle", x: 900, y: 110, s1: 1.5 },
        { t: 0.7, type: "heart", x: 620, y: 250, s1: 1.2 },
      ],
      linger: { rootYBounceAmp: 9, rootYBounceHz: 2.4 },
      fxLoop: { every: 1.1, type: "sparkle", x: 980, y: 190, s1: 1.3, life: 1.4 },
    }),

    playful: E({
      zh: "調皮", emoji: "😜", group: "正向",
      face: { eyeOpen: 1.05, squintR: 0.08, eyeArc: 1, mOpen: 0.4, mWide: 0.9, mCurve: 0.8, blush: 1.15, pupilX: 0.4 },
      clip: MOTION.sway(1.2, 2, 0.42),
      fx: [{ t: 0.3, type: "note", x: 1000, y: 240, s1: 1.2 }],
      linger: { rootRotSwayAmp: 2.4, rootRotSwayHz: 0.9 },
    }),

    mischief: E({
      zh: "惡作劇", emoji: "😈", group: "正向",
      face: { eyeOpen: 0.55, browShow: 0.9, browTilt: 0.8, mCurve: 0.9, mWide: 0.75, mOpen: 0.15, blush: 0.9, pupilX: -0.5 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.4, ch: { rootRot: -2.5, rootY: 5, sy: -0.03, sx: 0.03 } },
        { t: 1.6, ch: { rootRot: -2.5, rootY: 5, sy: -0.03, sx: 0.03 } },
        { t: 1.9, ch: { rootY: -18, sy: 0.05 } },
        { t: 2.3, ch: {} },
      ],
      fx: [{ t: 1.85, type: "sparkle", x: 1010, y: 220, s1: 1.3 }],
      linger: { rootRotSwayAmp: 1.4, rootRotSwayHz: 0.8 },
    }),

    proud: E({
      zh: "得意", emoji: "😎", group: "正向",
      face: { eyeOpen: 0.5, eyeArc: 0.6, browShow: 0.5, browTilt: 0.3, mCurve: 0.85, mWide: 0.45, blush: 0.85 },
      clip: MOTION.puff(1, 2.6),
      fx: [{ t: 0.35, type: "sparkle", x: 1010, y: 250, s1: 1.35 }],
      linger: { headRotBase: -1.5 },
    }),


    determined: E({
      zh: "有幹勁", emoji: "💪", group: "正向",
      face: { eyeOpen: 1.1, browShow: 1, browTilt: 0.55, mCurve: 0.5, mWide: 0.6, mOpen: 0.12, blush: 0.85 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.22, ch: { rootY: 8, sy: -0.05, sx: 0.04 } },
        { t: 0.45, ch: { rootY: -30, sy: 0.07, sx: -0.05 } },
        { t: 0.7, ch: { rootY: 0, sy: 0.03, sx: 0.02 } },
        { t: 2.2, ch: { rootY: 0, sy: 0.03, sx: 0.02 } },
        { t: 2.7, ch: {} },
      ],
      fx: [{ t: 0.45, type: "bang", x: 1015, y: 195, life: 1, s1: 1.1 }],
      linger: { rootYBounceAmp: 3, rootYBounceHz: 1.4 },
    }),


    // ============ 正向 · 柔和 ============
    calm: E({ zh: "平靜", emoji: "🙂", group: "柔和", face: {}, clip: MOTION.still(0.6) }),

    relaxed: E({
      zh: "放鬆", emoji: "😌", group: "柔和",
      face: { eyeOpen: 0.12, eyeArc: 0.8, mCurve: 0.5, mWide: 0.25, blush: 0.9 },
      clip: [
        { t: 0, ch: {} },
        { t: 1.1, ch: { sy: 0.03, headY: -3 } },
        { t: 2.3, ch: { sy: -0.02, headY: 6 } },
        { t: 3.4, ch: {} },
      ],
      linger: { rootRotSwayAmp: 1.1, rootRotSwayHz: 0.25 },
    }),

    relieved: E({
      zh: "鬆一口氣", emoji: "😮‍💨", group: "柔和",
      face: { eyeOpen: 0.14, eyeArc: 0.75, mOpen: 0.3, mWide: 0.3, mRound: 0.7, blush: 0.85 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.3, ch: { sy: 0.055, rootY: -8, headY: -4 } },
        { t: 1.2, ch: { sy: -0.045, sx: 0.03, rootY: 7, headY: 10 } },
        { t: 2.2, ch: { sy: -0.02, rootY: 3, headY: 5 } },
        { t: 3.0, ch: {} },
      ],
      fx: [{ t: 1.0, type: "drop", x: 960, y: 300, vy: -34, vx: 20, life: 1.3, s1: 1.1 }],
      linger: {},
    }),

    grateful: E({
      zh: "感動", emoji: "🥹", group: "柔和",
      face: { eyeOpen: 1.05, pupilScale: 1.15, browShow: 0.85, browTilt: -0.8, tear: 0.85, mCurve: 0.7, mWide: 0.35, blush: 1.2 },
      clip: MOTION.nod(0.8, 2),
      fx: [{ t: 0.4, type: "sparkle", x: 620, y: 330, s1: 1.1 }, { t: 0.9, type: "heart", x: 960, y: 300, s1: 1.2 }],
      linger: { rootRotSwayAmp: 1.2, rootRotSwayHz: 0.4 },
    }),

    touched: E({
      zh: "窩心", emoji: "🫶", group: "柔和",
      face: { eyeOpen: 0.15, eyeArc: 1, mCurve: 0.85, mWide: 0.3, blush: 1.35 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.6, ch: { headRot: 4, headY: 8, sy: 0.03 } },
        { t: 2.0, ch: { headRot: 4, headY: 8, sy: 0.03 } },
        { t: 2.7, ch: {} },
      ],
      fx: [{ t: 0.4, type: "heart", x: 580, y: 340, s1: 1.3, life: 1.8 },
           { t: 1.0, type: "heart", x: 960, y: 320, s1: 1.15, life: 1.7 }],
      linger: { headRotBase: 3, rootRotSwayAmp: 1.3, rootRotSwayHz: 0.35 },
    }),

    love: E({
      zh: "心動", emoji: "🥰", group: "柔和",
      face: { eyeOpen: 0.1, eyeArc: 1, mCurve: 0.95, mWide: 0.4, blush: 1.6 },
      clip: MOTION.sway(0.9, 2, 0.6),
      fx: [
        { t: 0.2, type: "heart", x: 570, y: 320, s1: 1.4, life: 1.9 },
        { t: 0.7, type: "heart", x: 980, y: 290, s1: 1.25, life: 1.8 },
        { t: 1.2, type: "heart", x: 780, y: 200, s1: 1.5, life: 2 },
      ],
      linger: { rootRotSwayAmp: 2, rootRotSwayHz: 0.45 },
      fxLoop: { every: 1.6, type: "heart", x: 990, y: 300, s1: 1.2, life: 1.8 },
    }),

    admiring: E({
      zh: "崇拜", emoji: "😻", group: "柔和",
      face: { eyeOpen: 1.3, pupilScale: 1.3, mOpen: 0.35, mWide: 0.5, mRound: 0.5, mCurve: 0.6, blush: 1.3, pupilY: -0.25 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.4, ch: { headY: -8, rootY: -12, sy: 0.05 } },
        { t: 2.2, ch: { headY: -8, rootY: -12, sy: 0.05 } },
        { t: 2.8, ch: {} },
      ],
      fx: [{ t: 0.2, type: "sparkle", x: 600, y: 250, s1: 1.4 },
           { t: 0.6, type: "sparkle", x: 950, y: 230, s1: 1.4 },
           { t: 1.1, type: "sparkle", x: 780, y: 160, s1: 1.5 }],
      linger: {},
      fxLoop: { every: 1.3, type: "sparkle", x: 1000, y: 230, s1: 1.3, life: 1.4 },
    }),

    hopeful: E({
      zh: "期待", emoji: "🤗", group: "柔和",
      face: { eyeOpen: 1.18, pupilScale: 1.15, mOpen: 0.25, mWide: 0.6, mCurve: 0.75, blush: 1.05, pupilY: -0.2 },
      clip: MOTION.hop(0.7, 3),
      fx: [{ t: 0.25, type: "sparkle", x: 1000, y: 240, s1: 1.15 }],
      linger: { rootYBounceAmp: 6, rootYBounceHz: 1.8 },
    }),


    apologetic: E({
      zh: "道歉", emoji: "😔", group: "柔和",
      face: { eyeOpen: 0.5, browShow: 0.95, browTilt: -0.85, mCurve: -0.4, mWide: 0.2, blush: 0.75, pupilY: 0.5 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.45, ch: { headY: 26, headRot: -3, rootY: 9, sy: -0.05 } },
        { t: 1.8, ch: { headY: 26, headRot: -3, rootY: 9, sy: -0.05 } },
        { t: 2.4, ch: { headY: 14, headRot: -2, rootY: 4 } },
      ],
      fx: [{ t: 0.8, type: "drop", x: 980, y: 300, vy: -18, life: 1.2, s1: 1.1 }],
      linger: { headYBase: 12, headRotBase: -2 },
    }),

    // ============ 負向 · 低落 ============
    sad: E({
      zh: "難過", emoji: "😢", group: "低落",
      face: { eyeOpen: 0.55, browShow: 1, browTilt: -1, tear: 0.9, mCurve: -0.85, mWide: 0.25, blush: 0.4, pupilY: 0.35 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.7, ch: { headRot: -4, headY: 16, sy: -0.03, rootY: 6 } },
        { t: 1.8, ch: { headRot: -4, headY: 16, sy: -0.03, rootY: 6, rootRot: -1.5 } },
        { t: 2.9, ch: { headRot: -4, headY: 16, sy: -0.03, rootY: 6, rootRot: 1.5 } },
        { t: 4.0, ch: { headRot: -4, headY: 16, sy: -0.03, rootY: 6 } },
      ],
      fx: [{ t: 1.1, type: "drop", x: 640, y: 470, vy: 40, vx: -6, gravity: 60, life: 1.2, s1: 1.1 }],
      linger: { headRotBase: -4, headYBase: 16, rootRotSwayAmp: 1.2, rootRotSwayHz: 0.3 },
    }),

    crying: E({
      zh: "大哭", emoji: "😭", group: "低落",
      face: { eyeOpen: 0.05, eyeArc: -1, browShow: 1, browTilt: -1, tear: 1, mOpen: 0.8, mWide: 0.75, mCurve: -1, blush: 0.9 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.3, ch: { headRot: -3, headY: 10, sy: -0.05, rootY: 8 } },
        { t: 0.8, ch: { headY: 4, sy: 0.03, rootY: -4 } },
        { t: 1.3, ch: { headY: 12, sy: -0.05, rootY: 8 } },
        { t: 1.9, ch: { headY: 4, sy: 0.03, rootY: -4 } },
        { t: 3.4, ch: { headY: 10, sy: -0.03, rootY: 5 } },
      ],
      tremble: 1.6,
      fx: [
        { t: 0.2, type: "drop", x: 636, y: 450, vy: 90, vx: -34, gravity: 80, life: 1.1, s1: 1.4 },
        { t: 0.5, type: "drop", x: 908, y: 450, vy: 90, vx: 34, gravity: 80, life: 1.1, s1: 1.4 },
        { t: 0.9, type: "drop", x: 636, y: 450, vy: 90, vx: -30, gravity: 80, life: 1.1, s1: 1.3 },
        { t: 1.3, type: "drop", x: 908, y: 450, vy: 90, vx: 30, gravity: 80, life: 1.1, s1: 1.3 },
      ],
      linger: { headYBase: 10, trembleAmp: 1.2, trembleHz: 9 },
      fxLoop: { every: 0.55, type: "drop", x: 908, y: 450, vy: 90, vx: 30, gravity: 80, life: 1.1, s1: 1.3 },
    }),

    disappointed: E({
      zh: "失望", emoji: "😞", group: "低落",
      face: { eyeOpen: 0.35, eyeArc: -0.5, browShow: 0.9, browTilt: -0.6, mCurve: -0.6, mWide: 0.2, blush: 0.5, pupilY: 0.6 },
      clip: MOTION.droop(1.15, 3.2),
      linger: { headRotBase: -3.5, headYBase: 18 },
    }),

    hurt: E({
      zh: "受傷", emoji: "💔", group: "低落",
      face: { eyeOpen: 0.75, pupilScale: 0.85, browShow: 1, browTilt: -0.95, tear: 0.6, mCurve: -0.75, mWide: 0.18, blush: 0.45, pupilY: 0.2 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.14, ch: { rootY: 6, sy: -0.05, sx: 0.04, headY: 8 } },
        { t: 0.7, ch: { headRot: -3, headY: 16, rootY: 6, sy: -0.03, rootRot: -2 } },
        { t: 3.0, ch: { headRot: -3, headY: 16, rootY: 6, sy: -0.03, rootRot: -2 } },
        { t: 3.6, ch: { headRot: -2, headY: 12 } },
      ],
      fx: [{ t: 0.1, type: "bang", x: 1000, y: 260, life: 1, s1: 1 }],
      linger: { headRotBase: -2, headYBase: 12, rootRotSwayAmp: 0.9, rootRotSwayHz: 0.28 },
    }),

    lonely: E({
      zh: "寂寞", emoji: "🥺", group: "低落",
      face: { eyeOpen: 1.1, pupilScale: 1.25, browShow: 0.9, browTilt: -0.85, mCurve: -0.4, mWide: 0.16, blush: 0.7, pupilY: 0.3 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.8, ch: { headRot: -3, headY: 12, sy: -0.03, rootX: -10, rootRot: -2 } },
        { t: 3.4, ch: { headRot: -3, headY: 12, sy: -0.03, rootX: -10, rootRot: -2 } },
        { t: 4.0, ch: { headRot: -2, headY: 9 } },
      ],
      linger: { headRotBase: -2, headYBase: 9, rootRotSwayAmp: 1, rootRotSwayHz: 0.22 },
    }),

    guilty: E({
      zh: "愧疚", emoji: "😖", group: "低落",
      face: { eyeOpen: 0.08, eyeArc: -0.7, browShow: 1, browTilt: -0.7, mCurve: -0.5, mWide: 0.55, sweat: 0.8, blush: 0.9 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.5, ch: { headRot: -3, headY: 20, sy: -0.05, sx: 0.04, rootY: 8 } },
        { t: 2.6, ch: { headRot: -3, headY: 20, sy: -0.05, sx: 0.04, rootY: 8 } },
        { t: 3.2, ch: { headY: 12 } },
      ],
      tremble: 1.1,
      linger: { headYBase: 12, trembleAmp: 0.9, trembleHz: 8 },
    }),

    bored: E({
      zh: "無聊", emoji: "😑", group: "低落",
      face: { eyeOpen: 0.3, eyeArc: 0, browShow: 0.4, browTilt: -0.1, mCurve: 0, mWide: 0.35, blush: 0.55, pupilX: -0.55, pupilY: 0.2 },
      clip: [
        { t: 0, ch: {} },
        { t: 1.0, ch: { headRot: 4, headY: 10, sy: -0.03 } },
        { t: 2.4, ch: { headRot: -4, headY: 10, sy: -0.03 } },
        { t: 3.8, ch: { headRot: 3, headY: 8, sy: -0.02 } },
      ],
      linger: { headYBase: 8, rootRotSwayAmp: 1.5, rootRotSwayHz: 0.18 },
    }),

    sulking: E({
      zh: "鬧脾氣", emoji: "😾", group: "低落",
      face: { eyeOpen: 0.3, eyeArc: 0, browShow: 1, browTilt: 0.6, mCurve: -0.7, mWide: 0.3, blush: 0.85, pupilX: -0.7 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.35, ch: { headRot: -6, rootRot: -3, rootX: -12, sx: 0.04, sy: -0.03 } },
        { t: 2.8, ch: { headRot: -6, rootRot: -3, rootX: -12, sx: 0.04, sy: -0.03 } },
        { t: 3.3, ch: { headRot: -4, rootRot: -2 } },
      ],
      linger: { headRotBase: -4 },
    }),

    // ============ 負向 · 高張力 ============
    angry: E({
      zh: "生氣", emoji: "😠", group: "高張力",
      face: { eyeOpen: 0.62, browShow: 1, browTilt: 1, blush: 0, mCurve: -0.7, mWide: 0.5, pupilScale: 0.9 },
      clip: MOTION.jitter(1, 2.2),
      fx: [{ t: 0.18, type: "anger", x: 1020, y: 200 }, { t: 1.1, type: "anger", x: 1020, y: 200 }],
      linger: { trembleAmp: 1.1, trembleHz: 11 },
    }),

    furious: E({
      zh: "暴怒", emoji: "🤬", group: "高張力",
      face: { eyeOpen: 0.7, browShow: 1, browTilt: 1, blush: 0, mOpen: 0.7, mWide: 0.8, mCurve: -0.9, pupilScale: 0.75 },
      clip: MOTION.jitter(1.6, 2.6),
      tremble: 3,
      fx: [
        { t: 0.08, type: "anger", x: 1020, y: 190, s1: 1.5 },
        { t: 0.5, type: "anger", x: 545, y: 210, s1: 1.4 },
        { t: 1.0, type: "bang", x: 1000, y: 150, s1: 1.3 },
        { t: 1.5, type: "anger", x: 1020, y: 190, s1: 1.5 },
      ],
      linger: { trembleAmp: 2.4, trembleHz: 15 },
      fxLoop: { every: 0.8, type: "anger", x: 1020, y: 195, s1: 1.4, life: 1.2 },
    }),

    annoyed: E({
      zh: "不爽", emoji: "😤", group: "高張力",
      face: { eyeOpen: 0.4, eyeArc: 0, browShow: 1, browTilt: 0.75, mCurve: -0.5, mWide: 0.35, blush: 0.5, pupilY: 0.15 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.35, ch: { sy: 0.05, rootY: -8 } },
        { t: 0.75, ch: { sy: -0.03, rootY: 5, sx: 0.03 } },
        { t: 2.4, ch: { sy: -0.02, rootY: 3 } },
        { t: 2.9, ch: {} },
      ],
      fx: [{ t: 0.75, type: "drop", x: 985, y: 300, vy: -26, vx: 18, life: 1.1, s1: 1.2 }],
      linger: { trembleAmp: 0.6, trembleHz: 7 },
    }),

    jealous: E({
      zh: "吃醋", emoji: "😒", group: "高張力",
      face: { eyeOpen: 0.35, squintL: 0.7, browShow: 0.95, browTilt: 0.5, mCurve: -0.45, mWide: 0.28, blush: 1.15, pupilX: 0.65 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.5, ch: { headRot: 5, rootRot: 2, sx: 0.03, sy: -0.02 } },
        { t: 2.6, ch: { headRot: 5, rootRot: 2, sx: 0.03, sy: -0.02 } },
        { t: 3.1, ch: { headRot: 3 } },
      ],
      fx: [{ t: 0.6, type: "anger", x: 560, y: 240, s1: 1 }],
      linger: { headRotBase: 3 },
    }),

    disgusted: E({
      zh: "嫌棄", emoji: "🤢", group: "高張力",
      face: { eyeOpen: 0.28, squintR: 0.5, browShow: 0.95, browTilt: 0.4, mCurve: -0.8, mWide: 0.45, blush: 0.35, pupilX: -0.6, pupilY: -0.2 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.3, ch: { headRot: -5, headX: -12, rootX: -10, sx: 0.04, sy: -0.04 } },
        { t: 2.3, ch: { headRot: -5, headX: -12, rootX: -10, sx: 0.04, sy: -0.04 } },
        { t: 2.9, ch: {} },
      ],
      linger: { headRotBase: -3.5 },
    }),

    suspicious: E({
      zh: "懷疑", emoji: "🧐", group: "高張力",
      face: { eyeOpen: 0.36, squintL: 0.45, browShow: 1, browTilt: 0.3, mCurve: -0.2, mWide: 0.2, blush: 0.6, pupilX: 0.6 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.6, ch: { headRot: 4, headX: 8 } },
        { t: 1.6, ch: { headRot: -4, headX: -8 } },
        { t: 2.6, ch: { headRot: 3, headX: 6 } },
        { t: 3.2, ch: { headRot: 2 } },
      ],
      fx: [{ t: 0.7, type: "quest", x: 1010, y: 200, vy: -30, life: 1.7, s1: 1.1 }],
      linger: { headRotBase: 2 },
    }),

    // ============ 驚嚇 · 慌張 ============
    surprised: E({
      zh: "驚訝", emoji: "😲", group: "驚嚇",
      face: { eyeOpen: 1.3, pupilScale: 0.8, browShow: 0.9, browTilt: -0.2, mOpen: 0.85, mWide: 0.35, mRound: 0.85, mCurve: 0, blush: 0.5 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.12, ch: { rootY: -60, sy: 0.09, sx: -0.06 } },
        { t: 0.3, ch: { rootY: -46, sy: 0.07, sx: -0.05 } },
        { t: 0.46, ch: { rootY: 0, sy: -0.06, sx: 0.06 } },
        { t: 0.64, ch: { rootY: -10, sy: 0.02 } },
        { t: 0.8, ch: {} },
      ],
      fx: [{ t: 0.06, type: "bang", x: 1010, y: 170, vy: -30, life: 1.15 }],
      linger: {},
    }),

    shocked: E({
      zh: "震驚", emoji: "😱", group: "驚嚇",
      face: { eyeOpen: 1.35, pupilScale: 0.45, browShow: 1, browTilt: -0.5, mOpen: 1, mWide: 0.3, mRound: 1, mCurve: -0.3, blush: 0.2, sweat: 0.9 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.1, ch: { rootY: -70, sy: 0.11, sx: -0.08 } },
        { t: 0.26, ch: { rootY: -55, sy: 0.08, sx: -0.06 } },
        { t: 0.44, ch: { rootY: 10, sy: -0.08, sx: 0.08 } },
        { t: 0.7, ch: { rootY: 6, sy: -0.04, sx: 0.04 } },
        { t: 2.6, ch: { rootY: 6, sy: -0.04, sx: 0.04 } },
        { t: 3.1, ch: {} },
      ],
      tremble: 3.2,
      fx: [{ t: 0.04, type: "bang", x: 1010, y: 150, vy: -40, life: 1.3, s1: 1.5 },
           { t: 0.3, type: "bang", x: 545, y: 180, vy: -34, life: 1.2, s1: 1.3 }],
      linger: { trembleAmp: 2.6, trembleHz: 16 },
    }),

    scared: E({
      zh: "害怕", emoji: "😨", group: "驚嚇",
      face: { eyeOpen: 1.15, pupilScale: 0.55, browShow: 1, browTilt: -0.7, mOpen: 0.3, mWide: 0.4, mCurve: -0.6, blush: 0.3, sweat: 1, pupilY: -0.15 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.18, ch: { rootRot: -4, rootX: -16, rootY: 4, sy: -0.04 } },
        { t: 3.2, ch: { rootRot: -4, rootX: -16, rootY: 4, sy: -0.04 } },
        { t: 3.7, ch: {} },
      ],
      tremble: 2.4,
      fx: [{ t: 0.4, type: "drop", x: 985, y: 290, vy: -20, life: 1.1, s1: 1.4 },
           { t: 1.6, type: "drop", x: 975, y: 300, vy: -20, life: 1.1, s1: 1.4 }],
      linger: { trembleAmp: 2.2, trembleHz: 13 },
    }),

    panic: E({
      zh: "慌張", emoji: "😵", group: "驚嚇",
      face: { eyeOpen: 1.3, pupilScale: 0.5, browShow: 1, browTilt: -0.6, mOpen: 0.6, mWide: 0.8, mCurve: -0.4, sweat: 1, blush: 0.6 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.18, ch: { rootX: -20, rootRot: -4 } },
        { t: 0.36, ch: { rootX: 20, rootRot: 4 } },
        { t: 0.54, ch: { rootX: -18, rootRot: -3.5 } },
        { t: 0.72, ch: { rootX: 18, rootRot: 3.5 } },
        { t: 0.9, ch: { rootX: -12, rootRot: -2 } },
        { t: 1.1, ch: { rootX: 0, rootRot: 0 } },
        { t: 2.4, ch: {} },
      ],
      tremble: 2.8,
      // 第三顆原本是思考點點，但它落在頭的右半邊、直接畫在臉上，所以拿掉
      fx: [{ t: 0.2, type: "drop", x: 985, y: 290, vy: -30, vx: 22, life: 1, s1: 1.3 },
           { t: 0.6, type: "drop", x: 560, y: 290, vy: -30, vx: -22, life: 1, s1: 1.3 }],
      linger: { trembleAmp: 2.4, trembleHz: 18 },
    }),

    nervous: E({
      zh: "緊張", emoji: "😬", group: "驚嚇",
      face: { eyeOpen: 0.95, pupilScale: 0.7, browShow: 0.9, browTilt: -0.4, mOpen: 0.18, mWide: 0.95, mCurve: -0.2, sweat: 0.85, blush: 0.8 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.4, ch: { sy: -0.03, sx: 0.03, rootY: 5, headY: 6 } },
        { t: 2.8, ch: { sy: -0.03, sx: 0.03, rootY: 5, headY: 6 } },
        { t: 3.3, ch: {} },
      ],
      tremble: 1.4,
      fx: [{ t: 0.9, type: "drop", x: 980, y: 300, vy: -18, life: 1.2, s1: 1.15 }],
      linger: { trembleAmp: 1.3, trembleHz: 14 },
    }),

    embarrassed: E({
      zh: "尷尬", emoji: "😅", group: "驚嚇",
      face: { eyeOpen: 0.1, eyeArc: 0.9, mOpen: 0.3, mWide: 0.9, mCurve: 0.4, sweat: 1, blush: 1.4 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.4, ch: { headRot: 5, headY: 6, rootRot: 2 } },
        { t: 1.2, ch: { headRot: -4, headY: 6, rootRot: -2 } },
        { t: 2.0, ch: { headRot: 4, headY: 5, rootRot: 1.5 } },
        { t: 2.8, ch: { headRot: 3, headY: 4 } },
      ],
      fx: [{ t: 0.5, type: "drop", x: 985, y: 285, vy: -22, vx: 16, life: 1.1, s1: 1.25 }],
      linger: { headRotBase: 3, rootRotSwayAmp: 1.8, rootRotSwayHz: 0.6 },
    }),

    dizzy: E({
      zh: "頭暈", emoji: "😵‍💫", group: "驚嚇",
      face: { eyeOpen: 0.06, eyeArc: 0.4, browShow: 0.5, browTilt: -0.3, mOpen: 0.35, mWide: 0.5, mRound: 0.5, mCurve: -0.2, blush: 1 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.7, ch: { headRot: 6, rootRot: 2.5, sy: -0.02 } },
        { t: 1.4, ch: { headRot: -6, rootRot: -2.5, sy: -0.02 } },
        { t: 2.1, ch: { headRot: 6, rootRot: 2.5, sy: -0.02 } },
        { t: 2.8, ch: { headRot: -5, rootRot: -2, sy: -0.02 } },
        { t: 3.5, ch: {} },
      ],
      fx: [{ t: 0.3, type: "sparkle", x: 830, y: 180, spin: 220, life: 1.6 },
           { t: 0.8, type: "sparkle", x: 720, y: 170, spin: -220, life: 1.6 }],
      linger: { rootRotSwayAmp: 2.4, rootRotSwayHz: 0.7 },
      fxLoop: { every: 0.9, type: "sparkle", x: 800, y: 175, spin: 260, life: 1.5, s1: 1.1 },
    }),

    // ============ 疑問 · 思考 ============
    confused: E({
      zh: "疑惑", emoji: "🤔", group: "思考",
      face: { squintR: 0.45, browShow: 0.85, browTilt: 0.25, mOpen: 0, mCurve: 0, mWide: 0.25, pupilX: -0.4, pupilY: -0.3 },
      clip: MOTION.tilt(1, 2.6),
      fx: [{ t: 0.45, type: "quest", x: 1010, y: 190, vy: -40, life: 1.9 }],
      linger: { headRotBase: 5.5 },
    }),

    thinking: E({
      zh: "思考", emoji: "💭", group: "思考",
      face: { eyeOpen: 0.55, squintL: 0.7, browShow: 0.6, browTilt: 0.15, mCurve: 0.1, mWide: 0.18, pupilX: -0.6, pupilY: -0.55 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.6, ch: { headRot: 4, headY: 5 } },
        { t: 2.0, ch: { headRot: -3, headY: 5 } },
        { t: 3.4, ch: { headRot: 3, headY: 4 } },
      ],
      // 緊張改用冷汗，而且擺在頭的外側（頭右緣 x≈1037）——
      // 原本的思考點點在 x=1005，那是臉上，不是頭旁邊
      fx: [{ t: 0.5, type: "drop", x: 1078, y: 190, vy: -18, vx: 14, life: 1.2, s1: 1.1 }],
      linger: { headRotBase: 2.5 },
      fxLoop: { every: 1.6, type: "drop", x: 1078, y: 190, vy: -18, vx: 14, life: 1.2, s1: 1.1 },
    }),

    curious: E({
      zh: "好奇", emoji: "👀", group: "思考",
      face: { eyeOpen: 1.25, pupilScale: 1.15, mOpen: 0.15, mWide: 0.3, mRound: 0.6, mCurve: 0.3, blush: 0.85 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.35, ch: { headRot: 5, headX: 10, headY: -6, rootY: -8 } },
        { t: 1.3, ch: { headRot: -5, headX: -10, headY: -6, rootY: -8 } },
        { t: 2.3, ch: { headRot: 4, headX: 8, headY: -4 } },
        { t: 3.0, ch: {} },
      ],
      fx: [{ t: 0.4, type: "quest", x: 1005, y: 205, vy: -30, life: 1.5, s1: 1 }],
      linger: { headRotBase: 2 },
    }),

    // ============ 生理狀態 ============
    sleepy: E({
      zh: "想睡", emoji: "😴", group: "生理",
      face: { eyeOpen: 0.2, eyeArc: 0.05, mOpen: 0, mCurve: 0.15, mWide: 0.15, blush: 0.55, pupilY: 0.3 },
      clip: [
        { t: 0, ch: {} },
        { t: 1.2, ch: { headRot: 3, headY: 20, sy: -0.02 } },
        { t: 2.4, ch: { headRot: -2, headY: 8, sy: -0.01 } },
        { t: 3.8, ch: { headRot: 4, headY: 24, sy: -0.025 } },
        { t: 5.0, ch: { headRot: -1, headY: 10 } },
      ],
      loop: true,
      fx: [{ t: 0.8, type: "zzz", x: 1000, y: 210, vy: -46, vx: 26, life: 2.2 }],
      linger: { headYBase: 14 },
      fxLoop: { every: 2.3, type: "zzz", x: 1000, y: 210, vy: -46, vx: 26, life: 2.2 },
    }),

    exhausted: E({
      zh: "累癱", emoji: "🥱", group: "生理",
      face: { eyeOpen: 0.07, eyeArc: -0.4, browShow: 0.6, browTilt: -0.5, mOpen: 0.55, mWide: 0.35, mRound: 0.75, blush: 0.6 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.9, ch: { headY: 26, headRot: -3, sy: -0.07, sx: 0.055, rootY: 12 } },
        { t: 3.4, ch: { headY: 26, headRot: -3, sy: -0.07, sx: 0.055, rootY: 12 } },
        { t: 4.0, ch: { headY: 20, sy: -0.05, sx: 0.04, rootY: 9 } },
      ],
      fx: [{ t: 0.7, type: "drop", x: 985, y: 300, vy: -14, life: 1.4, s1: 1.1 }],
      linger: { headYBase: 20, rootRotSwayAmp: 0.9, rootRotSwayHz: 0.2 },
    }),

    hungry: E({
      zh: "肚子餓", emoji: "🍽", group: "生理",
      face: { eyeOpen: 0.85, browShow: 0.7, browTilt: -0.55, mOpen: 0.4, mWide: 0.4, mRound: 0.4, mCurve: -0.3, blush: 0.7, pupilY: 0.25 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.5, ch: { sy: -0.05, sx: 0.045, rootY: 8, headY: 10 } },
        { t: 0.9, ch: { sy: -0.02, sx: 0.02, rootY: 4, headY: 6 } },
        { t: 1.4, ch: { sy: -0.05, sx: 0.045, rootY: 8, headY: 10 } },
        { t: 2.6, ch: { sy: -0.03, rootY: 5, headY: 7 } },
        { t: 3.2, ch: {} },
      ],
      fx: [{ t: 0.5, type: "note", x: 800, y: 700, vy: -40, life: 1.3, s1: 1 }],
      linger: { headYBase: 6 },
    }),


    cold: E({
      zh: "好冷", emoji: "🥶", group: "生理",
      face: { eyeOpen: 0.15, eyeArc: -0.6, browShow: 0.85, browTilt: -0.5, mOpen: 0.16, mWide: 0.85, mCurve: -0.4, blush: 1.15 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.3, ch: { sy: -0.06, sx: 0.05, rootY: 10, headY: 14 } },
        { t: 3.2, ch: { sy: -0.06, sx: 0.05, rootY: 10, headY: 14 } },
        { t: 3.8, ch: {} },
      ],
      tremble: 3.4,
      fx: [{ t: 0.3, type: "flake", x: 620, y: 200, vy: 70, life: 1.8, s1: 1.2 },
           { t: 0.9, type: "flake", x: 930, y: 170, vy: 70, life: 1.8, s1: 1.1 }],
      linger: { trembleAmp: 3, trembleHz: 19, headYBase: 10 },
      fxLoop: { every: 1.0, type: "flake", x: 880, y: 180, vy: 70, life: 1.8, s1: 1.1 },
    }),

    hot: E({
      zh: "好熱", emoji: "🥵", group: "生理",
      face: { eyeOpen: 0.12, eyeArc: -0.5, browShow: 0.8, browTilt: -0.6, mOpen: 0.55, mWide: 0.6, mRound: 0.3, mCurve: -0.2, sweat: 1, blush: 1.5 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.8, ch: { headRot: 4, headY: 14, sy: -0.05, sx: 0.045, rootY: 8 } },
        { t: 1.9, ch: { headRot: -4, headY: 14, sy: -0.05, sx: 0.045, rootY: 8 } },
        { t: 3.0, ch: { headRot: 3, headY: 12, sy: -0.04, sx: 0.035, rootY: 6 } },
        { t: 3.8, ch: {} },
      ],
      fx: [{ t: 0.5, type: "drop", x: 975, y: 290, vy: 26, vx: 12, gravity: 40, life: 1.2, s1: 1.3 },
           { t: 1.5, type: "drop", x: 575, y: 300, vy: 26, vx: -12, gravity: 40, life: 1.2, s1: 1.3 }],
      linger: { headYBase: 10, rootRotSwayAmp: 1.6, rootRotSwayHz: 0.35 },
      fxLoop: { every: 1.2, type: "drop", x: 975, y: 290, vy: 26, vx: 12, gravity: 40, life: 1.2, s1: 1.3 },
    }),

    sick: E({
      zh: "不舒服", emoji: "🤒", group: "生理",
      face: { eyeOpen: 0.1, eyeArc: -0.8, browShow: 1, browTilt: -0.75, mOpen: 0.2, mWide: 0.3, mCurve: -0.7, sweat: 0.9, blush: 1.35 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.9, ch: { headRot: -3, headY: 22, sy: -0.06, rootY: 11 } },
        { t: 3.4, ch: { headRot: -3, headY: 22, sy: -0.06, rootY: 11 } },
        { t: 4.0, ch: { headY: 18, sy: -0.04, rootY: 8 } },
      ],
      tremble: 1.2,
      fx: [{ t: 0.8, type: "drop", x: 980, y: 295, vy: -16, life: 1.3, s1: 1.15 }],
      linger: { headYBase: 18, trembleAmp: 1, trembleHz: 8, rootRotSwayAmp: 1.1, rootRotSwayHz: 0.24 },
    }),

    // ============ 社交 ============
    shy: E({
      zh: "害羞", emoji: "😳", group: "社交",
      face: { eyeOpen: 0.62, blush: 1.6, pupilX: 0.7, pupilY: 0.45, mCurve: 0.55, mWide: 0.2, mOpen: 0 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.6, ch: { headRot: 6, headY: 10, rootRot: 2 } },
        { t: 1.6, ch: { headRot: 6, headY: 10, rootRot: -2 } },
        { t: 2.6, ch: { headRot: 6, headY: 10, rootRot: 2 } },
        { t: 3.4, ch: { headRot: 5, headY: 8 } },
      ],
      fx: [{ t: 0.5, type: "heart", x: 560, y: 330, s1: 1.3, life: 1.7 }],
      linger: { headRotBase: 5, headYBase: 8, rootRotSwayAmp: 2, rootRotSwayHz: 0.4 },
    }),

    greeting: E({
      zh: "打招呼", emoji: "👋", group: "社交",
      face: { eyeOpen: 0.12, eyeArc: 1, mOpen: 0.45, mWide: 0.8, mCurve: 0.9, blush: 1.05 },
      clip: [
        { t: 0, ch: {} },
        { t: 0.25, ch: { rootRot: 2.8, rootY: -18, sy: 0.04 } },
        { t: 0.55, ch: { rootRot: -2.8, rootY: 0 } },
        { t: 0.85, ch: { rootRot: 2.8, rootY: -14, sy: 0.03 } },
        { t: 1.15, ch: { rootRot: 0, rootY: 0 } },
        { t: 1.6, ch: {} },
      ],
      fx: [{ t: 0.2, type: "sparkle", x: 1010, y: 250, s1: 1.1 }],
      linger: { rootRotSwayAmp: 2.2, rootRotSwayHz: 0.7 },
    }),


    agreeing: E({
      zh: "認同", emoji: "👍", group: "社交",
      face: { eyeOpen: 0.14, eyeArc: 0.9, mCurve: 0.75, mWide: 0.45, blush: 0.95 },
      clip: MOTION.nod(1, 3),
      linger: {},
    }),


  };

  PET.EMOTION_KEYS = Object.keys(PET.EMOTIONS);

  // 依分組列出，給 UI/驗貨面板用
  PET.EMOTION_GROUPS = (() => {
    const g = {};
    for (const k of PET.EMOTION_KEYS) (g[PET.EMOTIONS[k].group] ||= []).push(k);
    return g;
  })();
})();
