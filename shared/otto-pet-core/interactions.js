// interactions.js — 摸摸阿白：頭、耳朵、肚子、手，各有不同反應（tap 版）。
//
// 改寫自 ref/otto-bear-pet-main/pet-core/interactions.js（2026-08-19）。原版直接聽
// mount 的 pointer 事件、支援拖曳互動（甩頭暈、持續搔耳跟手）；但本專案的 renderer
// 是 `pointer-events: none` 的 sandbox iframe，指標事件由外層（web 的 BearStage）
// 攔下、換算成正規化座標後以 bridge 的 `poke` 指令送進來——與視線（look）、道具
// （tap）同一條路。故此版只保留「點一下」：部位判定、情緒、特效與釋放動畫照抄原版，
// 拖曳類互動（quickShake 甩頭、按著搔癢）等有需要再回去搬。
//
// 原版的 navigator.vibrate 刻意拿掉：sandbox iframe 裡沒有使用者啟動狀態
// （指令是 postMessage 進來的），呼叫只會被瀏覽器靜默忽略。
(function () {
  const PET = (window.PET = window.PET || {});

  const REACTIONS = {
    pet: {
      emotion: "happy", label: "被摸摸",
      lines: ["嗯～你的手好溫暖。", "嘿嘿，摸摸有充到電的感覺。", "再一下下就好，我很喜歡。"],
    },
    ear: {
      emotion: "shy", label: "耳朵好癢",
      lines: ["哈哈哈！耳朵好癢啦～", "那裡是我的怕癢開關！", "咿呀～耳朵會自己抖啦！"],
    },
    belly: {
      emotion: "excited", label: "戳到笑點",
      lines: ["噗～肚子也是怕癢區！", "嘿！被你找到笑點了。", "哈哈，這一下很突然耶！"],
    },
    hand: {
      emotion: "playful", label: "爪爪互動",
      lines: ["爪爪借你一下～", "要一起揮手或握手嗎？", "我的手套今天很有精神！"],
    },
  };

  const pick = (a) => a[Math.floor(Math.random() * a.length)];

  PET.Interactions = class {
    constructor(pet) {
      this.pet = pet;
      this.release = null;
      // pet.js 的渲染迴圈每一幀呼叫 `interaction.step(dt, P)`（釋放動畫靠它）。
      pet.interaction = this;
    }

    /**
     * 外層送進來的一下觸碰。`nx`／`ny` 是相對 iframe 的正規化座標（0–1）。
     * 回傳判到的部位（除錯與測試用）；沒打中或不該理時回 null。
     */
    poke(nx, ny) {
      const pet = this.pet;
      // 講話中、思考中不理（原版行為：對話永遠比玩重要）；聆聽中是本專案加的
      // ——長輩正在錄音，畫面不該多出會動的東西去搶注意力。
      if (pet.thinking || pet.talking || pet.listening) return null;
      const hit = this._hit(this._toUser(nx, ny));
      if (!hit) return null;
      pet.backToIdle();
      if (pet.idle) pet.idle.suspend();
      pet.userActivity();
      const kind = hit.zone === "head" ? "pet" : hit.zone;
      this._react(kind, hit.side);
      this.release = { kind, side: hit.side, t: 0 };
      return kind;
    }

    /** 正規化座標 → bear_svg 的使用者座標。CTM 反轉會自己吃掉任何縮放與留白。 */
    _toUser(nx, ny) {
      const svg = this.pet.svg;
      const m = svg.getScreenCTM();
      if (!m) return null;
      const p = svg.createSVGPoint();
      p.x = nx * window.innerWidth;
      p.y = ny * window.innerHeight;
      return p.matrixTransform(m.inverse());
    }

    // 部位範圍與原版一字未改（bear_svg 是同一份 1624×1128 的圖）。
    _hit(p) {
      if (!p) return null;
      if (p.y >= 185 && p.y <= 355 && p.x >= 515 && p.x <= 675)
        return { zone: "ear", side: -1 };
      if (p.y >= 185 && p.y <= 355 && p.x >= 900 && p.x <= 1045)
        return { zone: "ear", side: 1 };
      if (p.y >= 55 && p.y <= 585 && p.x >= 535 && p.x <= 1020)
        return { zone: "head", side: 0 };
      if (p.y >= 575 && p.y <= 975 && p.x >= 560 && p.x <= 980)
        return { zone: "belly", side: 0 };
      if (p.y >= 720 && p.y <= 955 && p.x >= 370 && p.x <= 560)
        return { zone: "hand", side: -1 };
      if (p.y >= 720 && p.y <= 955 && p.x >= 1000 && p.x <= 1200)
        return { zone: "hand", side: 1 };
      return null;
    }

    _react(kind, side) {
      const R = REACTIONS[kind] || REACTIONS.pet;
      this.pet.setEmotion(R.emotion, { intensity: kind === "belly" ? 2 : 1 });
      if (kind === "hand") {
        // 左手互動揮左手，右手互動做握手，讓觸碰位置直接對應手部動作。
        this.pet.playAction(side < 0 ? "wave_left" : "handshake", {
          duration: 1.8, amplitude: 0.68, speed: 0.9,
        });
      }
      const x = side < 0 ? 540 : side > 0 ? 1010 : 930;
      const y = kind === "ear" ? 245 : 315;
      if (kind === "ear") {
        this.pet.fx.spawn("sparkle", { x, y, life: 1.05, s1: 1.25 });
        this.pet.fx.spawn("note", { x: x + side * 35, y: y - 5, life: 1.2, s1: 1.15 });
      } else if (kind === "pet") {
        this.pet.fx.spawn("heart", { x, y, life: 1.55, s1: 1.35 });
      } else if (kind === "belly") {
        this.pet.fx.spawn("sparkle", { x: 820, y: 700, life: 1.1, s1: 1.45 });
      } else {
        this.pet.fx.spawn("bang", { x: 1010, y: 185, life: 0.95, s1: 1.05 });
      }
      this.pet._emit("interaction", {
        kind, label: R.label, emotion: R.emotion, text: pick(R.lines),
      });
    }

    // 釋放動畫（原版 step 的 release 段；拖曳中的即時跟手段落已隨拖曳一起拿掉）。
    step(dt, P) {
      const r = this.release;
      if (!r) return;
      r.t += dt;
      const fade = 1 - PET.smooth(PET.clamp(r.t / 0.9, 0, 1));
      if (r.kind === "ear") {
        P.headRot += r.side * 5 * fade + Math.sin(r.t * 42) * 4 * fade;
        P.rootX += Math.sin(r.t * 45) * 3 * fade;
      } else if (r.kind === "belly") {
        P.sx += Math.sin(r.t * 24) * 0.04 * fade;
        P.sy -= Math.sin(r.t * 24) * 0.035 * fade;
      } else if (r.kind === "hand") {
        if (r.side < 0) P.armLShoulder += (24 + Math.sin(r.t * 18) * 8) * fade;
        else P.armRShoulder -= (24 + Math.sin(r.t * 18) * 8) * fade;
      } else {
        P.headY += Math.sin(r.t * Math.PI) * 9 * fade;
      }
      if (r.t >= 0.9) {
        this.release = null;
        // 原版靠拖曳結束的游標流程回復待機；tap 版在演完的這一刻自己把待機還回去，
        // 否則 suspend 之後再也沒有人 resume，阿白從此不打盹也不玩小劇場。
        if (this.pet.idle) this.pet.idle.resume();
      }
    }
  };
})();
