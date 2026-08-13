// lipsync.js — 逐字打字機 + 注音嘴型驅動
(function () {
  const PET = (window.PET = window.PET || {});

  const PAUSE = { "，": 0.22, "、": 0.18, "。": 0.34, "！": 0.3, "？": 0.3, "…": 0.4, ",": 0.2, ".": 0.3, "!": 0.28, "?": 0.28, "~": 0.24, "～": 0.24 };

  PET.TalkDriver = class {
    constructor(pet) { this.pet = pet; this.active = null; }

    // talk(text, {durationMs, onChar(ch, i), onDone()}) — 逐字揭示 + 對嘴。
    // durationMs 由正式 TTS 回覆提供；有值時把每字節奏等比例拉到實際音檔長度。
    talk(text, cb = {}) {
      this.stop();
      const chars = Array.from(text);
      const charDelay = (ch) => PAUSE[ch] != null ? PAUSE[ch] : /[㐀-鿿]/.test(ch) ? 0.095 : 0.05;
      const baseSeconds = 0.15 + chars.reduce((sum, ch) => sum + charDelay(ch), 0);
      const requestedSeconds = Number(cb.durationMs) / 1000;
      const scale = Number.isFinite(requestedSeconds) && requestedSeconds > 0
        ? requestedSeconds / Math.max(baseSeconds, 0.15)
        : 1;
      this.active = { chars, i: 0, wait: 0.15 * scale, cb, decay: 0, scale, charDelay };
      this.pet.talkStart();
    }

    stop() {
      if (this.active) { this.active = null; this.pet.talkEnd(); }
    }

    step(dt) {
      const A = this.active;
      if (!A) return;
      A.wait -= dt;
      A.decay += dt;
      // 兩字之間嘴型自然回收
      if (A.decay > 0.1 && this.pet.faceS.mOpen.target > 0.14) {
        this.pet.faceS.mOpen.set(this.pet.faceS.mOpen.target * 0.55);
      }
      while (A.wait <= 0 && A.i < A.chars.length) {
        const ch = A.chars[A.i];
        const vis = window.visemeOf(ch);
        this.pet.talkChar(vis);
        if (A.cb.onChar) A.cb.onChar(ch, A.i);
        A.i++;
        A.decay = 0;
        A.wait += A.charDelay(ch) * A.scale;
      }
      if (A.i >= A.chars.length && A.wait > -0.35) {
        if (A.wait <= 0) {
          const cb = A.cb;
          this.active = null;
          this.pet.talkEnd();
          if (cb.onDone) cb.onDone();
        }
      }
    }
  };
})();
