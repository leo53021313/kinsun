// motion.js — Blend Tree 風格的程序式動作狀態機
(function () {
  const PET = (window.PET = window.PET || {});

  const STATE_LABEL = {
    idle: "待機", listening: "聆聽", thinking: "思考", speaking: "說話",
    emotion: "情緒", action: "動作", transition: "過場",
  };

  const GESTURE_ALIAS = {
    none: "none", wave: "wave", clap: "clap", dance: "dance", jump: "jump",
    hug: "hug", comforting: "comfort", comfort: "comfort", point: "point",
    beckon: "beckon", celebrate: "celebrate", walk: "walk", turn: "turn",
    nod: "nod", slow_nod: "nod", hands_forward: "comfort", pat: "pat",
    handshake: "handshake", high_five: "high_five", fist_bump: "fist_bump",
    thumbs_up: "thumbs_up", open_paws: "open_paws", offer_hand: "offer_hand",
    scratch_head: "scratch_head", finger_heart: "finger_heart",
    wave_left: "wave_left", wave_both: "wave_both",
  };

  // 新增的 10 種手部動作：共用同一套材質 Rig，不產生異質手部圖層。
  PET.HAND_GESTURES = Object.freeze([
    "handshake", "high_five", "fist_bump", "thumbs_up", "open_paws",
    "offer_hand", "scratch_head", "finger_heart", "wave_left", "wave_both",
  ]);

  function n(v, fallback, min, max) {
    const x = Number(v);
    return Number.isFinite(x) ? PET.clamp(x, min, max) : fallback;
  }

  PET.MOTION_GESTURES = Object.freeze(Object.keys(GESTURE_ALIAS));

  PET.AnimationStateMachine = class {
    constructor(pet) {
      this.pet = pet;
      this.state = "idle";
      this.previous = "idle";
      this.transition = 1;
      this.time = 0;
      this.intent = null;
      this.eventCount = 0;
    }

    set(state, meta = {}) {
      const next = STATE_LABEL[state] ? state : "idle";
      if (next !== this.state) {
        this.previous = this.state;
        this.state = next;
        this.transition = 0;
        this.eventCount++;
      }
      if (meta.intent) this.intent = meta.intent;
      this.pet?._emit("animation", {
        state: this.state, label: STATE_LABEL[this.state],
        previous: this.previous, transition: this.transition,
        eventCount: this.eventCount, intent: this.intent,
      });
    }

    setIntent(intent) {
      this.intent = intent || null;
      if (intent?.hand_gesture && intent.hand_gesture !== "none") this.set("action", { intent });
    }

    _gesture() {
      const raw = String(this.intent?.hand_gesture || "none").toLowerCase();
      return GESTURE_ALIAS[raw] || "none";
    }

    _amplitude() {
      return n(this.intent?.motion_amplitude, 0.58, 0.15, 1.2);
    }

    _speed() {
      return n(this.intent?.motion_speed, 0.68, 0.2, 1.4);
    }

    sample(dt, P) {
      this.time += dt;
      this.transition = PET.clamp(this.transition + dt * 5.2, 0, 1);
      const t = this.time;
      const qualityScale = this.pet?.motionQuality === "low" ? 0.68 : this.pet?.motionQuality === "balanced" ? 0.86 : 1;
      const a = this._amplitude() * qualityScale;
      const speed = this._speed();
      const wave = (hz, phase = 0) => Math.sin(t * hz * speed + phase);
      const g = this._gesture();
      const blend = PET.smooth(this.transition);

      // 脊椎、呼吸與重心是每個狀態都共享的底層 procedural layer。
      P.chestRot += wave(0.32) * 0.6 * a;
      P.sy += wave(0.58, 0.5) * 0.0035 * a;
      P.rootY -= Math.abs(wave(0.58)) * 1.7 * a;

      const posture = this.intent?.body_posture;
      if (posture === "slight_forward_lean" || posture === "comforting") {
        P.rootRot += 1.7 * a; P.headY += 2.5 * a;
      } else if (posture === "slight_back_lean" || posture === "proud") {
        P.rootRot -= 1.7 * a; P.headY -= 2.5 * a;
      } else if (posture === "shrink") {
        P.sy -= 0.02 * a; P.sx += 0.015 * a; P.rootY += 5 * a;
      } else if (posture === "open") {
        P.armLShoulder += 7 * a; P.armRShoulder -= 7 * a;
      }

      const head = this.intent?.head_motion;
      if (head === "slow_nod") P.headY += Math.abs(wave(0.8)) * 5 * a;
      else if (head === "nod") P.headY += Math.abs(wave(1.8)) * 11 * a;
      else if (head === "tilt_left") P.headRot -= 3.2 * a;
      else if (head === "tilt_right") P.headRot += 3.2 * a;
      else if (head === "look_up") P.headY -= 5 * a;
      else if (head === "look_down") P.headY += 5 * a;
      else if (head === "shake") P.headRot += wave(5.4) * 3.8 * a;

      if (this.state === "listening") {
        P.rootRot += wave(0.38) * 0.9 * a;
        P.headY += 5 + wave(0.7) * 1.8 * a;
        P.armLShoulder += 9 * a + wave(0.75) * 3;
        P.armRShoulder -= 9 * a + wave(0.75) * 3;
        P.armLElbow += 3 * a; P.armRElbow -= 3 * a;
      } else if (this.state === "thinking") {
        P.rootRot += wave(0.42) * 1.3 * a;
        P.headRot += 2.2 + wave(0.7) * 1.4 * a;
        P.headY += 5 + wave(0.54) * 2 * a;
        P.armLShoulder += 28 * a;
        P.armLElbow += 13 * a + wave(2.1) * 3;
        P.handLFlex += 0.04 * a;
      } else if (this.state === "speaking") {
        const beat = wave(1.25);
        P.rootRot += beat * 0.7 * a;
        P.headRot += wave(1.05, 0.5) * 1.3 * a;
        P.armLShoulder += beat * 8 * a;
        P.armRShoulder -= beat * 8 * a;
        P.armLElbow += wave(1.5, 0.8) * 4 * a;
        P.armRElbow -= wave(1.5, 0.8) * 4 * a;
        P.handLFlex += Math.max(0, beat) * 0.035 * a;
        P.handRFlex += Math.max(0, -beat) * 0.035 * a;
      } else if (this.state === "emotion" || this.state === "action") {
        this._sampleGesture(g, P, t, a, speed);
      } else if (this.state === "idle") {
        P.armLShoulder += wave(0.42) * 1.4 * a;
        P.armRShoulder -= wave(0.42) * 1.4 * a;
      }

      // 過場時將主要動作縮入，交給各通道 Spring 完成緩入／緩出。
      if (blend < 1) {
        const fade = blend;
        for (const key of ["rootRot", "headRot", "armLShoulder", "armRShoulder", "armLElbow", "armRElbow", "legLRot", "legRRot"]) {
          P[key] *= fade;
        }
      }
    }

    _sampleGesture(g, P, t, a, speed) {
      const s = (hz, phase = 0) => Math.sin(t * hz * speed + phase);
      switch (g) {
        case "wave":
          P.armRShoulder -= 48 * a + s(3.6) * 9 * a;
          P.armRElbow -= 20 * a + s(4.6) * 8 * a;
          P.handRFlex += 0.06 * Math.max(0, s(4.6));
          P.rootRot += s(0.7) * 1.3 * a;
          break;
        case "clap": {
          const beat = Math.abs(s(2.4));
          P.armLShoulder += 18 * a + beat * 16 * a;
          P.armRShoulder -= 18 * a + beat * 16 * a;
          P.armLElbow += beat * 10 * a; P.armRElbow -= beat * 10 * a;
          P.rootY -= beat * 7 * a;
          break;
        }
        case "dance":
          P.rootX += s(1.4) * 9 * a; P.rootRot += s(1.4) * 3.5 * a;
          P.armLShoulder += s(2.8) * 24 * a; P.armRShoulder -= s(2.8) * 24 * a;
          P.legLRot += s(2.8, 0.7) * 5 * a; P.legRRot -= s(2.8, 0.7) * 5 * a;
          P.rootY -= Math.max(0, s(2.8)) * 12 * a;
          break;
        case "jump":
        case "celebrate": {
          const beat = Math.max(0, s(2.1));
          P.rootY -= beat * (g === "jump" ? 34 : 18) * a;
          P.sy += beat * 0.045 * a; P.sx -= beat * 0.03 * a;
          P.armLShoulder += 36 * a + beat * 22 * a;
          P.armRShoulder -= 36 * a + beat * 22 * a;
          P.handLFlex += beat * 0.05; P.handRFlex += beat * 0.05;
          break;
        }
        case "hug":
          P.armLShoulder += 30 * a; P.armRShoulder -= 30 * a;
          P.armLElbow += 16 * a; P.armRElbow -= 16 * a;
          P.rootY += 3 * a; P.headY += s(0.7) * 1.4;
          break;
        case "comfort":
          P.armLShoulder += 24 * a; P.armRShoulder -= 24 * a;
          P.armLElbow += 8 * a; P.armRElbow -= 8 * a;
          P.rootRot += s(0.45) * 0.7 * a;
          break;
        case "point":
          P.armRShoulder -= 36 * a; P.armRElbow -= 26 * a;
          P.handRFlex += 0.05 * a; P.headRot += s(0.55) * 1.5 * a;
          break;
        case "beckon":
          P.armRShoulder -= 30 * a; P.armRElbow -= 18 * a;
          P.handRFlex += Math.max(0, s(2.6)) * 0.08 * a;
          break;
        case "walk": {
          const step = s(2.9);
          P.rootX += step * 8 * a; P.rootRot += step * 1.8 * a;
          P.legLRot += step * 7 * a; P.legRRot -= step * 7 * a;
          P.armLShoulder += step * 5 * a; P.armRShoulder -= step * 5 * a;
          P.rootY -= Math.max(0, step) * 3 * a;
          break;
        }
        case "turn":
          P.rootRot += s(0.8) * 7 * a; P.headRot -= s(0.8) * 3 * a;
          P.scarfRot += s(0.8, 0.9) * 5 * a;
          break;
        case "nod":
          P.headY += Math.abs(s(2.1)) * 13 * a; P.headRot += s(2.1) * 1.7 * a;
          break;
        case "pat":
          P.armLShoulder += 32 * a + s(3.2) * 5 * a;
          P.armLElbow += 20 * a + s(3.2) * 5 * a;
          break;
        case "handshake": {
          // 右手向前伸出，加入短促的上下握動與左手預備反應。
          const beat = s(3.8);
          P.armRShoulder -= 27 * a + beat * 4 * a;
          P.armRElbow -= 23 * a + beat * 8 * a;
          P.armLShoulder += 7 * a;
          P.handRFlex += 0.055 + Math.max(0, beat) * 0.035;
          P.rootY -= Math.max(0, beat) * 3 * a;
          break;
        }
        case "high_five": {
          const beat = Math.max(0, s(2.1));
          P.armRShoulder -= 48 * a + beat * 8 * a;
          P.armRElbow -= 17 * a + beat * 5 * a;
          P.handRFlex += 0.06 + Math.max(0, s(5.2)) * 0.04;
          P.rootRot += s(0.8) * 1.2 * a;
          break;
        }
        case "fist_bump": {
          const beat = Math.max(0, s(2.5));
          P.armRShoulder -= 32 * a + beat * 9 * a;
          P.armRElbow -= 21 * a;
          P.handRFlex += 0.1 * beat;
          P.rootY -= beat * 4 * a;
          break;
        }
        case "thumbs_up":
          P.armRShoulder -= 31 * a + s(0.6) * 2 * a;
          P.armRElbow -= 17 * a;
          P.handRFlex += 0.085;
          P.headRot += s(0.8) * 1.2 * a;
          break;
        case "open_paws":
          P.armLShoulder += 25 * a; P.armRShoulder -= 25 * a;
          P.armLElbow += 13 * a; P.armRElbow -= 13 * a;
          P.handLFlex += 0.08 + s(1.2) * 0.015;
          P.handRFlex += 0.08 - s(1.2) * 0.015;
          break;
        case "offer_hand":
          P.armRShoulder -= 26 * a + s(0.75) * 2 * a;
          P.armRElbow -= 25 * a;
          P.handRFlex += 0.05 + Math.max(0, s(2.8)) * 0.045;
          P.rootRot += s(0.55) * 0.8 * a;
          break;
        case "scratch_head":
          P.armLShoulder += 43 * a + s(2.8) * 4 * a;
          P.armLElbow += 25 * a + s(3.8) * 5 * a;
          P.handLFlex += 0.045 + Math.max(0, s(5.4)) * 0.055;
          P.headRot -= 2.2 * a;
          break;
        case "finger_heart": {
          const beat = s(1.4);
          P.armLShoulder += 18 * a; P.armRShoulder -= 18 * a;
          P.armLElbow += 21 * a; P.armRElbow -= 21 * a;
          P.handLFlex += 0.06 + beat * 0.018;
          P.handRFlex += 0.06 - beat * 0.018;
          P.rootY -= Math.max(0, beat) * 2 * a;
          break;
        }
        case "wave_left":
          P.armLShoulder += 48 * a + s(3.6) * 9 * a;
          P.armLElbow += 20 * a + s(4.6) * 8 * a;
          P.handLFlex += 0.06 * Math.max(0, s(4.6));
          P.rootRot -= s(0.7) * 1.3 * a;
          break;
        case "wave_both": {
          const beat = s(3.4);
          P.armLShoulder += 43 * a + beat * 6 * a;
          P.armRShoulder -= 43 * a - beat * 6 * a;
          P.armLElbow += 18 * a + s(4.4) * 6 * a;
          P.armRElbow -= 18 * a - s(4.4) * 6 * a;
          P.handLFlex += 0.055 * Math.max(0, s(4.7));
          P.handRFlex += 0.055 * Math.max(0, s(4.7, Math.PI));
          P.rootY -= Math.max(0, beat) * 3 * a;
          break;
        }
      }
    }
  };
})();
