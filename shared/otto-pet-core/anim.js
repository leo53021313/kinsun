// anim.js — 極簡彈簧/補間工具
(function () {
  const PET = (window.PET = window.PET || {});

  PET.clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  PET.lerp = (a, b, t) => a + (b - a) * t;
  PET.smooth = (t) => t * t * (3 - 2 * t);

  // 臨界阻尼彈簧
  PET.Spring = class {
    constructor(v = 0, k = 120, d = null) {
      this.v = v; this.target = v; this.vel = 0;
      this.k = k; this.d = d == null ? 2 * Math.sqrt(k) : d;
    }
    set(t) { this.target = t; return this; }
    snap(t) { this.v = this.target = t; this.vel = 0; return this; }
    step(dt) {
      dt = Math.min(dt, 0.05);
      this.vel += (this.k * (this.target - this.v) - this.d * this.vel) * dt;
      this.v += this.vel * dt;
      return this.v;
    }
  };

  // 關鍵影格剪輯: frames=[{t, ch:{k:v}}], 通道間平滑內插
  PET.Clip = class {
    constructor(frames, opts = {}) {
      this.frames = frames;
      this.dur = frames.length ? frames[frames.length - 1].t : 0;
      this.loop = !!opts.loop;
      this.fx = opts.fx || [];     // [{t, type, x, y}]
      this.tremble = opts.tremble || 0;
    }
    sample(t, out) {
      const F = this.frames;
      if (!F.length) return out;
      if (this.loop && this.dur > 0) t %= this.dur;
      if (t >= this.dur) t = this.dur;
      let i = 0;
      while (i < F.length - 1 && F[i + 1].t < t) i++;
      const a = F[i], b = F[Math.min(i + 1, F.length - 1)];
      const span = b.t - a.t;
      const u = span > 0 ? PET.smooth(PET.clamp((t - a.t) / span, 0, 1)) : 1;
      const keys = new Set([...Object.keys(a.ch || {}), ...Object.keys(b.ch || {})]);
      for (const k of keys) {
        const av = (a.ch && a.ch[k]) || 0, bv = (b.ch && b.ch[k]) || 0;
        out[k] = (out[k] || 0) + PET.lerp(av, bv, u);
      }
      return out;
    }
    done(t) { return !this.loop && t >= this.dur; }
  };

  // SVG transform 組字串（自算原點，避開各引擎 transform-origin 差異）
  PET.xform = function (el, { x = 0, y = 0, rot = 0, sx = 1, sy = 1, ox = 0, oy = 0 }) {
    el.setAttribute("transform",
      `translate(${x + ox},${y + oy}) rotate(${rot}) scale(${sx},${sy}) translate(${-ox},${-oy})`);
  };
})();
