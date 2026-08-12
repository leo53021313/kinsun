// behavior.js — LLM/本地規則共用的結構化行為契約與語意映射
(function () {
  const PET = (window.PET = window.PET || {});

  const VALID = {
    emotions: () => new Set(PET.EMOTION_KEYS || []),
    bodyStates: new Set(["neutral", "attentive", "thinking", "speaking", "comforting", "proud", "shy", "excited", "walking", "celebrating"]),
    facial: new Set(["neutral", "gentle_smile", "open_smile", "concerned", "surprised", "focused", "shy", "sleepy"]),
    head: new Set(["none", "slow_nod", "nod", "tilt_left", "tilt_right", "look_up", "look_down", "shake"]),
    gestures: new Set(["none", "wave", "clap", "dance", "jump", "hug", "comforting", "comfort", "point", "beckon", "celebrate", "walk", "turn", "nod", "slow_nod", "hands_forward", "pat", "handshake", "high_five", "fist_bump", "thumbs_up", "open_paws", "offer_hand", "scratch_head", "finger_heart", "wave_left", "wave_both"]),
    posture: new Set(["neutral", "relaxed", "slight_forward_lean", "slight_back_lean", "open", "shrink", "proud", "walking", "comforting"]),
    focus: new Set(["user", "camera", "left", "right", "up", "down", "away"]),
  };

  const EMOTION_DEFAULT = {
    happy: { gesture: "celebrate", facial: "gentle_smile", posture: "open" },
    excited: { gesture: "jump", facial: "open_smile", posture: "open" },
    celebrating: { gesture: "celebrate", facial: "open_smile", posture: "open" },
    greeting: { gesture: "wave", facial: "gentle_smile", posture: "open" },
    sad: { gesture: "comfort", facial: "concerned", posture: "shrink" },
    hurt: { gesture: "comfort", facial: "concerned", posture: "slight_forward_lean" },
    lonely: { gesture: "comfort", facial: "concerned", posture: "slight_forward_lean" },
    apologetic: { gesture: "nod", facial: "concerned", posture: "slight_forward_lean" },
    confused: { gesture: "none", facial: "focused", posture: "slight_forward_lean" },
    curious: { gesture: "point", facial: "focused", posture: "slight_forward_lean" },
    thinking: { gesture: "none", facial: "focused", posture: "slight_forward_lean" },
    nervous: { gesture: "none", facial: "concerned", posture: "shrink" },
    shy: { gesture: "none", facial: "shy", posture: "shrink" },
    angry: { gesture: "none", facial: "concerned", posture: "proud" },
    calm: { gesture: "none", facial: "neutral", posture: "relaxed" },
    relaxed: { gesture: "none", facial: "neutral", posture: "relaxed" },
  };

  const firstValid = (value, set, fallback) => set.has(value) ? value : fallback;

  PET.BEHAVIOR_SCHEMA = function () {
    return {
      type: "OBJECT",
      properties: {
        reply: { type: "STRING" }, audio: { type: "STRING" },
        primary_emotion: { type: "STRING", enum: PET.EMOTION_KEYS },
        secondary_emotion: { type: "STRING", enum: PET.EMOTION_KEYS },
        emotion_intensity: { type: "NUMBER" }, body_state: { type: "STRING" },
        facial_expression: { type: "STRING" }, head_motion: { type: "STRING" },
        hand_gesture: { type: "STRING" }, body_posture: { type: "STRING" },
        eye_focus: { type: "STRING" }, motion_speed: { type: "NUMBER" },
        motion_amplitude: { type: "NUMBER" }, duration: { type: "NUMBER" },
        priority: { type: "INTEGER" }, action: { type: "STRING" },
      },
      required: ["reply", "primary_emotion", "emotion_intensity", "body_state", "facial_expression", "head_motion", "hand_gesture", "body_posture", "eye_focus", "motion_speed", "motion_amplitude", "duration", "priority"],
    };
  };

  PET.normalizeBehavior = function (raw = {}) {
    const emotionSet = VALID.emotions();
    const selectedPrimary = firstValid(raw.primary_emotion || raw.emotion, emotionSet, "calm");
    const selectedSecondary = firstValid(raw.secondary_emotion, emotionSet, "calm");
    // sentiment.js 會在 runtime 初始化完成前載入；呼叫 normalizeBehavior 時再取函式，
    // 讓 LLM 與本地規則共用同一道最後防線。
    const primary = PET.sanitizeEmotion ? PET.sanitizeEmotion(selectedPrimary) : selectedPrimary;
    const secondary = PET.sanitizeEmotion ? PET.sanitizeEmotion(selectedSecondary) : selectedSecondary;
    const preset = EMOTION_DEFAULT[primary] || EMOTION_DEFAULT.calm;
    return {
      reply: String(raw.reply || "").slice(0, 240),
      audio: String(raw.audio || raw.reply || "").slice(0, 500),
      primary_emotion: primary, secondary_emotion: secondary,
      emotion_intensity: PET.clamp(Number(raw.emotion_intensity ?? raw.intensity ?? 2) || 2, 0, 1),
      body_state: firstValid(raw.body_state, VALID.bodyStates, "neutral"),
      facial_expression: firstValid(raw.facial_expression, VALID.facial, preset.facial),
      head_motion: firstValid(raw.head_motion, VALID.head, "none"),
      hand_gesture: firstValid(raw.hand_gesture || raw.gesture, VALID.gestures, preset.gesture),
      body_posture: firstValid(raw.body_posture || raw.posture, VALID.posture, preset.posture),
      eye_focus: firstValid(raw.eye_focus, VALID.focus, "user"),
      motion_speed: PET.clamp(Number(raw.motion_speed) || 0.68, 0.2, 1.4),
      motion_amplitude: PET.clamp(Number(raw.motion_amplitude) || 0.58, 0.15, 1.2),
      duration: PET.clamp(Number(raw.duration) || 3.6, 0.6, 18),
      priority: PET.clamp(Number(raw.priority) | 0 || 2, 0, 5),
      action: String(raw.action || raw.hand_gesture || "none"),
      emotion: primary, intensity: PET.clamp(Math.round((Number(raw.emotion_intensity) || 0.66) * 3), 1, 3),
      mode: raw.mode || "local",
    };
  };

  PET.behaviorFromEmotion = function (emotion, intensity = 2) {
    return PET.normalizeBehavior({
      primary_emotion: emotion, emotion_intensity: PET.clamp(intensity / 3, 0, 1),
    });
  };

  PET.BehaviorController = class {
    constructor(pet) { this.pet = pet; this.current = PET.normalizeBehavior({}); }
    begin(raw) {
      this.current = PET.normalizeBehavior(raw);
      this.pet.setMotionIntent(this.current);
      this.pet.lookAt(this.current.eye_focus === "user" || this.current.eye_focus === "camera" ? 0 : this.current.eye_focus === "left" ? -0.72 : this.current.eye_focus === "right" ? 0.72 : 0, this.current.eye_focus === "up" ? -0.65 : this.current.eye_focus === "down" ? 0.65 : 0);
      return this.current;
    }
    finish() {
      const b = this.current;
      this.pet.setEmotion(b.primary_emotion, { intensity: b.intensity });
      return b;
    }
  };
})();
