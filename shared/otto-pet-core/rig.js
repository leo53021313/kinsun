// rig.js — 角色 Rig 契約：2D 全身控制通道與可擴充骨架描述
(function () {
  const PET = (window.PET = window.PET || {});

  PET.RIG_VERSION = "otto-2d-full-body-v1";
  PET.RIG_CHANNELS = Object.freeze([
    "rootX", "rootY", "rootRot", "sx", "sy",
    "headRot", "headX", "headY", "chestRot",
    "armLShoulder", "armLElbow", "armRShoulder", "armRElbow",
    "handLFlex", "handRFlex", "legLRot", "legRRot", "footL", "footR", "scarfRot",
  ]);
  PET.RIG_BONES = Object.freeze({
    root: "腳底重心",
    spine: "胸口呼吸與身體重心",
    neck: "頭部樞紐與圍巾延遲",
    head: "頭部轉向／傾斜",
    eye: "視線與眨眼（face overlay）",
    mouth: "嘴型／對嘴（viseme）",
    armL: "左肩—左手掌",
    armR: "右肩—右手掌",
    legL: "左髖—左腳",
    legR: "右髖—右腳",
  });

  PET.RigContract = function () {
    return {
      version: PET.RIG_VERSION,
      channels: PET.RIG_CHANNELS.slice(),
      bones: { ...PET.RIG_BONES },
      capabilities: [
        "procedural_breathing", "spring_blend", "look_at", "viseme_lipsync",
        "gesture_library", "weight_shift", "event_driven_state_machine",
      ],
    };
  };
})();
