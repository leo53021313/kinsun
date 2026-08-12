// body.js — 高擬真身體材質上的 2D 程序式骨架
//
// 藝術版角色是一張透明 PNG。這裡把同一張 PNG 以「同材質裁切」拆成
// 軀幹、上肢／手掌與腿，所有動作仍使用原始針織紋理，不新增異畫風貼圖。
(function () {
  const PET = (window.PET = window.PET || {});
  const NS = "http://www.w3.org/2000/svg";

  const CLIPS = {
    // core 的上緣要高過頭部溶接帶的起點（y≈489），否則頭淡出的那一段後面沒有東西墊著，
    // 會直接透到背景。上緣本身永遠藏在不透明的頭部後面。
    core: `M 510 424 C 620 408 930 408 1065 440
      L 1065 972 C 930 996 650 996 510 972 Z`,
    armLUpper: `M 382 570 C 430 545 535 555 575 625
      L 575 830 C 532 862 425 864 390 820 Z`,
    armRUpper: `M 990 570 C 1040 548 1148 555 1195 592
      L 1188 820 C 1148 864 1040 862 995 830 Z`,
    handL: `M 370 760 C 400 735 510 742 555 800
      L 548 934 C 485 968 390 936 364 876 Z`,
    handR: `M 1000 800 C 1040 744 1145 736 1190 775
      L 1198 876 C 1170 938 1072 968 1008 934 Z`,
    legL: `M 520 858 C 575 840 690 840 755 865
      L 760 1128 L 515 1128 Z`,
    legR: `M 780 865 C 850 840 965 840 1020 858
      L 1025 1128 L 780 1128 Z`,
  };

  function svgEl(tag, attrs, parent) {
    const el = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs || {})) el.setAttribute(key, value);
    if (parent) parent.appendChild(el);
    return el;
  }

  PET.Body = class {
    constructor(parent, bodySrc) {
      this.g = bodySrc || null;
      this.svg = parent?.ownerSVGElement || null;
      this.bones = {};
      this.ready = false;
      if (this.g && this.g.parentNode !== parent) parent.appendChild(this.g);
      this._buildRasterRig(parent);
    }

    _buildRasterRig(parent) {
      const art = this.g?.querySelector?.("#bodyArt");
      if (!art || !this.svg) return;

      const defs = this.svg.querySelector("defs") || svgEl("defs", {}, this.svg);
      const clipIds = {};
      for (const [key, d] of Object.entries(CLIPS)) {
        const id = `ottoRig${key[0].toUpperCase()}${key.slice(1)}`;
        const old = this.svg.querySelector(`#${id}`);
        if (old) old.remove();
        const cp = svgEl("clipPath", { id }, defs);
        svgEl("path", { d }, cp);
        clipIds[key] = id;
      }

      // 原圖只保留軀幹與圍巾，四肢由下方同材質 bone group 顯示。
      art.setAttribute("clip-path", `url(#${clipIds.core})`);
      this.g.setAttribute("data-rig-layer", "body-core");

      const clone = (id, clip) => {
        const copy = art.cloneNode(true);
        copy.removeAttribute("id");
        copy.setAttribute("data-rig-source", id);
        copy.setAttribute("clip-path", `url(#${clipIds[clip]})`);
        return copy;
      };

      const legL = svgEl("g", { id: "rigLegL", "data-bone": "leg.L" });
      const legR = svgEl("g", { id: "rigLegR", "data-bone": "leg.R" });
      legL.appendChild(clone("legL", "legL"));
      legR.appendChild(clone("legR", "legR"));
      parent.insertBefore(legL, this.g);
      parent.insertBefore(legR, this.g);

      const armL = svgEl("g", { id: "rigArmL", "data-bone": "arm.L" });
      const armR = svgEl("g", { id: "rigArmR", "data-bone": "arm.R" });
      const handL = svgEl("g", { id: "rigHandL", "data-bone": "hand.L" });
      const handR = svgEl("g", { id: "rigHandR", "data-bone": "hand.R" });
      armL.appendChild(clone("armL", "armLUpper"));
      armR.appendChild(clone("armR", "armRUpper"));
      handL.appendChild(clone("handL", "handL"));
      handR.appendChild(clone("handR", "handR"));
      armL.appendChild(handL); armR.appendChild(handR);
      parent.appendChild(armL); parent.appendChild(armR);

      this.bones = {
        legL, legR, armL, armR, handL, handR,
        shoulderL: { x: 535, y: 615 }, shoulderR: { x: 1035, y: 615 },
        elbowL: { x: 468, y: 790 }, elbowR: { x: 1100, y: 790 },
        hipL: { x: 635, y: 900 }, hipR: { x: 890, y: 900 },
      };
      this.ready = true;
    }

    // 軀幹＋圍巾是同一塊針織布，所以整塊一起做連續形變，而不是切成幾片各動各的：
    //   剪力  x' = x + lean·(pivot − y)   下襬為 0、領口最大 → 布被頭帶著往旁邊延伸
    //   縱拉  y' = y·(1+s) − pivot·s      抬頭時脖子與領口跟著拉長
    // 兩者都是連續函數，任何一列都不會出現位移的跳階，因此不會有接縫或折角，
    // 也完全不需要另外疊一層外加的圍巾向量。
    applyCloth(p = {}) {
      if (!this.g) return;
      const pivot = Number.isFinite(p.clothPivot) ? p.clothPivot : 1010;
      const lean = PET.clamp(Number.isFinite(p.clothLean) ? p.clothLean : 0, -0.06, 0.06);
      const s = PET.clamp(Number.isFinite(p.clothStretch) ? p.clothStretch : 0, -0.03, 0.04);
      if (!lean && !s) {
        if (this._clothOn) { this.g.removeAttribute("transform"); this._clothOn = false; }
        return;
      }
      this._clothOn = true;
      const skew = (-Math.atan(lean) * 180) / Math.PI;
      this.g.setAttribute("transform",
        `translate(${(lean * pivot).toFixed(2)} 0) skewX(${skew.toFixed(4)}) ` +
        `translate(0 ${(-pivot * s).toFixed(2)}) scale(1 ${(1 + s).toFixed(5)})`);
    }

    apply(p = {}) {
      if (!this.ready) return this.applyCloth(p);
      this.applyCloth(p);
      const b = this.bones;
      const rot = (v, min, max) => PET.clamp(Number.isFinite(v) ? v : 0, min, max);
      const flex = (v) => PET.clamp(Number.isFinite(v) ? v : 0, -0.08, 0.1);

      PET.xform(b.legL, {
        rot: rot(p.legLRot, -13, 13), ox: b.hipL.x, oy: b.hipL.y,
        sx: 1 + flex(p.footL), sy: 1 - flex(p.footL) * 0.55,
      });
      PET.xform(b.legR, {
        rot: rot(p.legRRot, -13, 13), ox: b.hipR.x, oy: b.hipR.y,
        sx: 1 + flex(p.footR), sy: 1 - flex(p.footR) * 0.55,
      });

      const shoulderL = rot(p.armLShoulder, -58, 58);
      const shoulderR = rot(p.armRShoulder, -58, 58);
      PET.xform(b.armL, { rot: shoulderL, ox: b.shoulderL.x, oy: b.shoulderL.y });
      PET.xform(b.armR, { rot: shoulderR, ox: b.shoulderR.x, oy: b.shoulderR.y });
      PET.xform(b.handL, {
        rot: rot(p.armLElbow, -35, 35), ox: b.elbowL.x, oy: b.elbowL.y,
        sx: 1 + flex(p.handLFlex), sy: 1 - flex(p.handLFlex) * 0.5,
      });
      PET.xform(b.handR, {
        rot: rot(p.armRElbow, -35, 35), ox: b.elbowR.x, oy: b.elbowR.y,
        sx: 1 + flex(p.handRFlex), sy: 1 - flex(p.handRFlex) * 0.5,
      });
    }

    hitTest() { return null; }
  };
})();
