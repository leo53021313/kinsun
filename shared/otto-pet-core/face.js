// face.js — 程式繪製臉層（座標為 bear.svg 的 4x 空間）
(function () {
  const PET = (window.PET = window.PET || {});
  const NS = "http://www.w3.org/2000/svg";
  const C = { ink: "#0d0d0d", blush: "#ffc4bd", hi: "#ffffff", mouthIn: "#7c3a3a", tear: "#aee0f7" };

  // 臉部基準座標
  const EYE_L = { x: 672, y: 400 }, EYE_R = { x: 870, y: 400 };
  const NOSE = { x: 771, y: 428 };
  const MOUTH = { x: 771, y: 486 };
  const BLUSH_L = { x: 626, y: 450 }, BLUSH_R = { x: 916, y: 450 };

  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  PET.defaultFace = () => ({
    eyeOpen: 1,        // 0..1.3
    eyeArc: 0,         // 閉眼時弧度 +1=∩開心 0=平 -1=∪
    squintL: 1, squintR: 1, // 個別眼睛倍率（疑惑用）
    browShow: 0, browTilt: 0, // Tilt +1=生氣(內端下壓) -1=難過(內端上揚)
    pupilX: 0, pupilY: 0,     // -1..1
    pupilScale: 1,
    tear: 0, sweat: 0,
    blush: 0.75,              // 原圖常駐腮紅
    mOpen: 0, mWide: 0.3, mCurve: 0.55, mRound: 0.2,
  });

  PET.Face = class {
    constructor(parentG) {
      this.g = el("g", { id: "faceG" }, parentG);
      this.p = PET.defaultFace();       // 目前值（外部用彈簧餵）
      this._build();
      this.apply(this.p);
    }

    _build() {
      const g = this.g;
      // 與高保真毛流底圖接軌：保留程式控制，但讓五官具有柔和的
      // 漸層、反光與細輪廓，不再像單色貼紙浮在毛面上。
      const defs = el("defs", {}, g);
      const eyeGrad = el("radialGradient", {
        id: "ottoEyeGradient", cx: "35%", cy: "27%", r: "78%",
      }, defs);
      el("stop", { offset: "0%", "stop-color": "#6f5a51" }, eyeGrad);
      el("stop", { offset: "30%", "stop-color": "#241916" }, eyeGrad);
      el("stop", { offset: "100%", "stop-color": "#070606" }, eyeGrad);
      const noseGrad = el("radialGradient", {
        id: "ottoNoseGradient", cx: "34%", cy: "25%", r: "80%",
      }, defs);
      el("stop", { offset: "0%", "stop-color": "#88716a" }, noseGrad);
      el("stop", { offset: "36%", "stop-color": "#382623" }, noseGrad);
      el("stop", { offset: "100%", "stop-color": "#100b0b" }, noseGrad);
      const blushGrad = el("radialGradient", {
        id: "ottoBlushGradient", cx: "50%", cy: "48%", r: "62%",
      }, defs);
      el("stop", { offset: "0%", "stop-color": "#ffd9d2" }, blushGrad);
      el("stop", { offset: "100%", "stop-color": "#f3aaa1" }, blushGrad);

      // 腮紅
      this.blushL = el("ellipse", { cx: BLUSH_L.x, cy: BLUSH_L.y, rx: 33, ry: 19, fill: "url(#ottoBlushGradient)" }, g);
      this.blushR = el("ellipse", { cx: BLUSH_R.x, cy: BLUSH_R.y, rx: 33, ry: 19, fill: "url(#ottoBlushGradient)" }, g);

      // 眼睛（開眼橢圓+高光 / 閉眼弧線 兩套切換）
      this.eyes = {};
      for (const [key, A] of [["L", EYE_L], ["R", EYE_R]]) {
        const eg = el("g", {}, g);
        const open = el("g", {}, eg);
        const ball = el("ellipse", {
          cx: 0, cy: 0, rx: 21, ry: 23, fill: "url(#ottoEyeGradient)",
          stroke: "#392823", "stroke-width": 2,
        }, open);
        const hi1 = el("circle", { cx: -7, cy: -8, r: 7, fill: C.hi }, open);
        const hi2 = el("circle", { cx: 6, cy: 7, r: 3.2, fill: C.hi, opacity: 0.9 }, open);
        const closed = el("path", {
          d: "", fill: "none", stroke: C.ink, "stroke-width": 7.5, "stroke-linecap": "round",
        }, eg);
        const brow = el("path", {
          d: "", fill: "none", stroke: C.ink, "stroke-width": 7, "stroke-linecap": "round", opacity: 0,
        }, eg);
        const tear = el("ellipse", { cx: key === "L" ? -16 : 16, cy: 22, rx: 9, ry: 12, fill: C.tear, opacity: 0 }, eg);
        this.eyes[key] = { eg, open, ball, hi1, hi2, closed, brow, tear, A };
      }

      // 鼻 + 人中 + 嘴
      this.nose = el("path", {
        d: `M ${NOSE.x - 26} ${NOSE.y - 10}
            Q ${NOSE.x} ${NOSE.y - 22} ${NOSE.x + 26} ${NOSE.y - 10}
            Q ${NOSE.x + 30} ${NOSE.y - 2} ${NOSE.x + 6} ${NOSE.y + 12}
            Q ${NOSE.x} ${NOSE.y + 15} ${NOSE.x - 6} ${NOSE.y + 12}
            Q ${NOSE.x - 30} ${NOSE.y - 2} ${NOSE.x - 26} ${NOSE.y - 10} Z`,
        fill: "url(#ottoNoseGradient)", stroke: "#2d1d1b", "stroke-width": 2,
      }, g);
      this.stem = el("path", {
        d: `M ${NOSE.x} ${NOSE.y + 12} L ${NOSE.x} ${MOUTH.y - 14}`,
        stroke: C.ink, "stroke-width": 6.5, "stroke-linecap": "round", fill: "none",
      }, g);
      this.mouthOpen = el("path", { d: "", fill: C.mouthIn, stroke: C.ink, "stroke-width": 6 }, g);
      this.mouthLine = el("path", { d: "", fill: "none", stroke: C.ink, "stroke-width": 7, "stroke-linecap": "round" }, g);

      // 汗滴（額頭右側）
      this.sweatDrop = el("path", {
        d: "M 940 300 q 14 20 0 30 q -14 -10 0 -30 Z",
        fill: C.tear, stroke: "#7cc4e8", "stroke-width": 2, opacity: 0,
      }, g);
    }

    apply(p) {
      this.p = p;
      // --- 眼睛 ---
      for (const key of ["L", "R"]) {
        const E = this.eyes[key];
        const openV = PET.clamp(p.eyeOpen * (key === "L" ? p.squintL : p.squintR), 0, 1.35);
        const px = p.pupilX * 9, py = p.pupilY * 8;
        PET.xform(E.eg, { x: E.A.x + px * 0.4, y: E.A.y + py * 0.4 });
        if (openV > 0.24) {
          E.open.setAttribute("display", "");
          E.closed.setAttribute("display", "none");
          const rx = 21 * p.pupilScale * (1 + (openV - 1) * 0.35);
          const ry = 23 * openV * p.pupilScale;
          E.ball.setAttribute("rx", rx); E.ball.setAttribute("ry", ry);
          PET.xform(E.open, { x: px * 0.6, y: py * 0.6 });
          E.hi1.setAttribute("r", 7 * p.pupilScale * PET.clamp(openV, 0.6, 1.15));
        } else {
          E.open.setAttribute("display", "none");
          E.closed.setAttribute("display", "");
          const w = 24, arc = p.eyeArc;
          // ∩ (arc>0) / 平 / ∪ (arc<0)
          E.closed.setAttribute("d",
            `M ${-w} ${arc * 6} Q 0 ${-arc * 22} ${w} ${arc * 6}`);
        }
        // 眉毛：短弧，browTilt>0 內端下壓(生氣) / <0 內端上揚(難過)
        const bs = p.browShow;
        E.brow.setAttribute("opacity", bs.toFixed(2));
        if (bs > 0.02) {
          const y0 = -46 - 8 * bs;
          const ang = p.browTilt * (key === "L" ? 18 : -18);
          E.brow.setAttribute("d", `M -21 ${y0} q 21 -7 42 0`);
          E.brow.setAttribute("transform", `rotate(${ang.toFixed(1)} 0 ${y0})`);
        }
        E.tear.setAttribute("opacity", (p.tear * (key === "L" ? 1 : 0.85)).toFixed(2));
        if (p.tear > 0.02) E.tear.setAttribute("cy", 22 + p.tear * 8);
      }

      // --- 腮紅 ---
      const b = PET.clamp(p.blush, 0, 1.6);
      for (const [elm, base] of [[this.blushL, BLUSH_L], [this.blushR, BLUSH_R]]) {
        elm.setAttribute("opacity", PET.clamp(b, 0, 1).toFixed(2));
        elm.setAttribute("rx", 33 * (0.8 + 0.35 * b));
        elm.setAttribute("ry", 19 * (0.8 + 0.35 * b));
      }

      // --- 嘴 ---
      const { mOpen: o, mWide: w, mCurve: c, mRound: r } = p;
      if (o < 0.12) {
        this.mouthOpen.setAttribute("display", "none");
        this.mouthLine.setAttribute("display", "");
        const y = MOUTH.y;
        if (c >= 0.15) {         // ω 微笑
          const hw = 46 + 26 * w, d = 16 + 14 * c;
          this.mouthLine.setAttribute("d",
            `M ${MOUTH.x - hw} ${y - d * 0.45} Q ${MOUTH.x - hw / 2} ${y + d} ${MOUTH.x} ${y}
             Q ${MOUTH.x + hw / 2} ${y + d} ${MOUTH.x + hw} ${y - d * 0.45}`);
        } else if (c <= -0.15) { // 下彎
          const hw = 34 + 18 * w, d = 10 + 22 * -c;
          this.mouthLine.setAttribute("d",
            `M ${MOUTH.x - hw} ${y + 6} Q ${MOUTH.x} ${y + 6 - d} ${MOUTH.x + hw} ${y + 6}`);
        } else {                  // 平
          const hw = 26 + 20 * w;
          this.mouthLine.setAttribute("d", `M ${MOUTH.x - hw} ${y + 2} L ${MOUTH.x + hw} ${y + 2}`);
        }
      } else {
        this.mouthLine.setAttribute("display", "none");
        this.mouthOpen.setAttribute("display", "");
        const rx = (26 + 34 * w) * (1 - 0.45 * r) + 6;
        const ry = (14 + 44 * o);   // 上限壓在圍巾備份帶之上，張大嘴不被身層蓋到
        const cy = MOUTH.y + 4 + ry * 0.32;
        const topDip = -c * 10; // 微笑開口: 上緣上彎
        this.mouthOpen.setAttribute("d",
          `M ${MOUTH.x - rx} ${cy - ry * 0.28}
           Q ${MOUTH.x} ${cy - ry * 0.55 + topDip} ${MOUTH.x + rx} ${cy - ry * 0.28}
           Q ${MOUTH.x + rx * 1.06} ${cy + ry * 0.55} ${MOUTH.x} ${cy + ry * 0.72}
           Q ${MOUTH.x - rx * 1.06} ${cy + ry * 0.55} ${MOUTH.x - rx} ${cy - ry * 0.28} Z`);
      }

      // 嘴角的實際座標：口水要真的從那裡流出來，所以每次畫完嘴就記下來。
      // 這幾條式子跟上面畫嘴的完全對應——閉嘴時是曲線的端點，
      // 張嘴時是橢圓開口的左右端點。用固定座標會在張嘴／笑開時對不上。
      if (o < 0.12) {
        const hw = c >= 0.15 ? 46 + 26 * w : (c <= -0.15 ? 34 + 18 * w : 26 + 20 * w);
        const dy = c >= 0.15 ? -(16 + 14 * c) * 0.45 : (c <= -0.15 ? 6 : 2);
        this.corner = { x: MOUTH.x + hw, y: MOUTH.y + dy, open: 0 };
      } else {
        const rx = (26 + 34 * w) * (1 - 0.45 * r) + 6;
        const ry = 14 + 44 * o;
        const cy = MOUTH.y + 4 + ry * 0.32;
        this.corner = { x: MOUTH.x + rx, y: cy - ry * 0.28, open: o };
      }

      // 汗滴
      this.sweatDrop.setAttribute("opacity", PET.clamp(p.sweat, 0, 1).toFixed(2));
    }

    // 右嘴角現在在哪（bear.svg 座標，未套用頭部 transform）
    mouthCorner() {
      return this.corner || { x: MOUTH.x + 46, y: MOUTH.y - 7, open: 0 };
    }
  };
})();
