// quality.js — Runtime 動畫品質驗證與自我修正
(function () {
  const PET = (window.PET = window.PET || {});

  PET.AnimationQuality = class {
    constructor(pet) {
      this.pet = pet; this.frames = 0; this.failures = 0; this.last = null;
      this.max = 0;
    }

    validate(P) {
      this.frames++;
      const failures = [];
      for (const key of PET.RIG_CHANNELS || []) {
        if (!Number.isFinite(P[key])) failures.push(`${key}:NaN`);
      }
      const bounded = [
        ["headRot", -8, 8], ["headX", -18, 18], ["armLShoulder", -64, 64],
        ["armRShoulder", -64, 64], ["legLRot", -16, 16], ["legRRot", -16, 16],
        ["motion_amplitude", 0, 1.2],
      ];
      for (const [key, min, max] of bounded) {
        if (Number.isFinite(P[key]) && (P[key] < min || P[key] > max)) failures.push(`${key}:bound`);
      }
      if (failures.length) {
        this.failures += failures.length;
        for (const key of PET.RIG_CHANNELS || []) if (!Number.isFinite(P[key])) P[key] = 0;
        for (const [key, min, max] of bounded) if (Number.isFinite(P[key])) P[key] = PET.clamp(P[key], min, max);
      }
      this.last = { frame: this.frames, failures, state: this.pet.stateMachine?.state || "idle" };
      return failures.length === 0;
    }

    report() {
      return {
        version: "quality-v1", frames: this.frames, repaired: this.failures,
        last: this.last, state: this.pet.stateMachine?.state || "idle",
        rig: PET.RIG_VERSION,
      };
    }
  };
})();
