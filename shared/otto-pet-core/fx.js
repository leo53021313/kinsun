// fx.js — 漂浮特效粒子（愛心/星星/淚滴/怒氣/驚嘆/問號/Zzz/雪花/音符/思考點點）
//         + 會沿路徑飛的小生物（蜜蜂/蝴蝶/蜻蜓）
//
// 兩種畫風，因為它們是不同的東西：
//   · 符號＝**寫實霓虹燈**。造型是一條「彎成那個形狀的玻璃管」中心線，
//     這裡把它疊成「遠場泛光→近場光暈→未點亮的玻璃→管→芯」五段。
//   · 小生物＝**可愛寫實**。比例誇張（頭大眼大）但上色是真的光影（漸層、
//     高光、遮蔽、透光），SVG 直接寫在 fx_art.js 裡。
// 規格見 upgrate/Knowledge Base/neon-critter-fx.md。
//
// 例外是口水（droolStrand / drip）：那是液體，不是訊號也不是生物，
// 維持既有的程序化流體幾何（透明、黏稠、重力下垂、表面高光）。
(function () {
  const PET = (window.PET = window.PET || {});
  const NS = "http://www.w3.org/2000/svg";

  const ART = PET.FX_ART || { neon: {}, sym: {}, critter: {} };

  // 霓虹要留得下光暈。一個 60 單位的符號在舊的 s1=2.1 下只有 46px，
  // 管徑不到 4px、芯不到 1.5px，芯會被管吃掉就只剩「一條有顏色的線」。
  // 放大 1.5 倍之後管約 5.8px、芯約 2.1px，五層才各自讀得出來。
  const FX_SCALE = 1.5;

  // 光暈的衰減：六層漸寬的描邊疊出近似高斯的累積不透明度
  // （由外而內累積約 0.05 → 0.11 → 0.18 → 0.26 → 0.35 → 0.46）。
  // 不用 feGaussianBlur 是刻意的：filter 的 id 得掛在文件層，符號一旦快取成
  // 字串就會跨 Fx 實例指到別人的 defs；而且這裡每層只差約 0.3 個管徑、
  // 透明度只差 0.1，在 6px 的管上看不出分層。
  // 最內圈是 1.65 而不是 1.4：玻璃那層是 1.5 個管徑，畫在光暈之上，
  // 1.4 會整層被它蓋掉——白畫一層還讓衰減斷一階。
  const BLOOM = [[4.6, 0.05], [3.7, 0.062], [3.0, 0.078],
                 [2.45, 0.098], [2.0, 0.125], [1.65, 0.16]];

  // 把一組「霓虹管」組成 SVG。管徑沿路徑不得變化——那是霓虹跟「發光的線」
  // 唯一真正的差別：招牌是把一根固定口徑的玻璃管折出來的。
  // 圓帽與圓角接合同時處理了兩件事：玻璃折不出尖角，而開放端的圓頭就是電極。
  function neonTube(parts) {
    let out = "";
    for (const part of parts || []) {
      const [glow, tube, core, glass] = ART.neon[part.c] || ["#888", "#aaa", "#fff", "#222"];
      const w = part.w, d = part.d;
      let s = '<g fill="none" stroke-linecap="round" stroke-linejoin="round">';
      for (const [k, op] of BLOOM) {
        s += `<path d="${d}" stroke="${glow}" stroke-width="${(w * k).toFixed(2)}"` +
          ` stroke-opacity="${op}"/>`;
      }
      // 未點亮的玻璃管壁：真招牌上看得到玻璃本身，管的最外緣有一圈比背景暗的線。
      // 它同時是淺色天空下的救命稻草——沒有它，亮色霓虹在淺藍底上會糊掉。
      s += `<path d="${d}" stroke="${glass}" stroke-width="${(w * 1.5).toFixed(2)}"` +
        ' stroke-opacity=".26"/>';
      s += `<path d="${d}" stroke="${tube}" stroke-width="${w}"/>`;
      // 芯：氣柱中央亮度遠高於邊緣，眼睛會把它削到接近白
      s += `<path d="${d}" stroke="${core}" stroke-width="${(w * 0.36).toFixed(2)}"/>`;
      out += s + "</g>";
    }
    return out;
  }

  // 氣體放電不是恆定的，但乾淨的正弦是呼吸燈不是霓虹，所以用兩個不可通約的
  // 頻率相加得到不規律的 ±7%。另外剛點亮的前 0.18 秒抖幾下——真的霓虹起輝
  // 時會閃，而粒子的生命剛好從那一刻開始，這一下不用另外排程就有了。
  function flicker(t) {
    const strike = t < 0.18 && Math.sin(t * 96) < -0.15 ? 0.3 : 1;
    return strike * (0.93 + 0.045 * Math.sin(t * 27.3) + 0.025 * Math.sin(t * 11.7 + 1.7));
  }

  const SYM_CACHE = {};
  function sym(type) {
    if (SYM_CACHE[type] === undefined) SYM_CACHE[type] = neonTube(ART.sym[type]);
    return SYM_CACHE[type];
  }

  // 口水斷掉往下掉的那一滴：跟掛著的那條同一套玻璃質感，不走點描
  const DRIP =
    '<g>' +
    '<path d="M0 -13 q 9.5 15 9 22.5 a 9 9.6 0 1 1 -18 0 q -0.5 -7.5 9 -22.5 Z" ' +
    'fill="#d8f0ff" fill-opacity=".62" stroke="#8fc7e6" stroke-opacity=".5" stroke-width="1.4"/>' +
    '<ellipse cx="-3" cy="6" rx="3" ry="4.4" fill="#ffffff" fill-opacity=".8" ' +
    'transform="rotate(-18 -3 6)"/>' +
    '<ellipse cx="4" cy="11" rx="1.6" ry="2.2" fill="#ffffff" fill-opacity=".5"/>' +
    "</g>";

  // ---------- 會飛的小生物 ----------
  // 這些跟上面的粒子不同：粒子是「噴出去就自己飄走」，小生物要沿著一條路徑飛、
  // 翅膀還要拍，所以做成常駐元件由待機動畫每一幀自己餵座標（見 idle.js）。
  // 翅膀是獨立的 <g class="wg">，每幀用 scale(n, 1) 收攏再張開就是拍翅。
  //
  // 每一隻自己帶一份 <defs>：漸層是靠 id 引用的，共用 id 的話同時飛兩隻
  // 就會其中一隻找不到自己的漸層（第一隻被移除時 defs 也跟著走）。
  function critterSvg(type, uid) {
    const c = ART.critter[type];
    if (!c) return "";
    const sub = (s) => (s || "").split("{U}").join(uid);
    return `<defs>${sub(c.defs)}</defs>` +
      `<g class="wg wl">${sub(c.wingL)}</g>` +
      `<g class="wg wr">${sub(c.wingR)}</g>` +
      sub(c.body);
  }

  PET.CRITTER_KEYS = Object.keys(ART.critter);

  PET.Fx = class {
    constructor(layerG) { this.g = layerG; this.live = []; }

    spawn(type, o = {}) {
      const e = document.createElementNS(NS, "g");
      const isDrip = type === "drip";
      e.innerHTML = isDrip ? DRIP : (sym(type) || sym("sparkle"));
      this.g.appendChild(e);
      const p = {
        e, t: 0, lit: !isDrip,     // 口水那一滴不是燈管，不閃
        life: o.life || 1.5,
        x: o.x == null ? 980 : o.x, y: o.y == null ? 260 : o.y,
        vx: o.vx == null ? 12 : o.vx, vy: o.vy == null ? -66 : o.vy,
        sway: o.sway == null ? 14 : o.sway, swayHz: o.swayHz || 2.1,
        s0: (o.s0 == null ? 0.5 : o.s0) * FX_SCALE,
        s1: (o.s1 == null ? 2.1 : o.s1) * FX_SCALE,
        spin: o.spin || 0, fadeIn: 0.12,
        gravity: o.gravity || 0,
      };
      this.live.push(p);
      return p;
    }

    step(dt) {
      for (let i = this.live.length - 1; i >= 0; i--) {
        const p = this.live[i];
        p.t += dt;
        if (p.t >= p.life) { p.e.remove(); this.live.splice(i, 1); continue; }
        p.vy += p.gravity * dt;
        p.x += p.vx * dt; p.y += p.vy * dt;
        const u = p.t / p.life;
        const sc = PET.lerp(p.s0, p.s1, Math.min(1, u * 3));
        const wob = Math.sin(p.t * Math.PI * 2 * p.swayHz) * p.sway;
        const op = p.t < p.fadeIn ? p.t / p.fadeIn : 1 - PET.smooth(Math.max(0, (u - 0.62) / 0.38));
        p.e.setAttribute("transform",
          `translate(${(p.x + wob).toFixed(1)},${p.y.toFixed(1)}) scale(${sc.toFixed(3)}) rotate(${(p.spin * p.t).toFixed(1)})`);
        // 霓虹的閃爍疊在淡入淡出上：粒子出現的瞬間剛好就是燈管起輝的瞬間
        p.e.setAttribute("opacity", PET.clamp(op * (p.lit ? flicker(p.t) : 1), 0, 1).toFixed(2));
      }
    }

    // 放一隻會飛的小生物出來。回傳一個 handle，待機動畫每一幀呼叫 at() 餵座標；
    // 翅膀的拍動由 handle 自己算，呼叫端只要負責路徑。
    critter(type) {
      const e = document.createElementNS(NS, "g");
      const uid = "ct" + (Fx._uid = (Fx._uid || 0) + 1);
      e.innerHTML = critterSvg(type, uid) || critterSvg("bee", uid);
      this.g.appendChild(e);
      const wings = e.querySelectorAll(".wg");
      const hz = type === "bee" ? 17 : type === "dfly" ? 13 : 5.5;   // 蜜蜂拍最快、蝴蝶最慢
      const self = {
        e, gone: false,
        // x,y = 位置；ang = 機身角度（度）；sc = 大小；t = 累計時間（決定翅膀相位）
        at(x, y, ang, sc, t, alpha) {
          if (self.gone) return;
          e.setAttribute("transform",
            `translate(${x.toFixed(1)},${y.toFixed(1)}) rotate(${(ang || 0).toFixed(1)}) ` +
            `scale(${(sc == null ? 1 : sc).toFixed(3)})`);
          e.setAttribute("opacity", alpha == null ? 1 : PET.clamp(alpha, 0, 1).toFixed(2));
          // 從上往下看，拍翅是翅膀往身體「收攏」——所以壓的是 X 不是 Y。
          // 壓 Y 會讓四片翅膀擠成一團，蝴蝶看起來就變成一朵花了。
          // 蝴蝶翅膀大、收得明顯；蜜蜂與蜻蜓拍太快，只需要一點殘影感。
          const w = type === "bfly" ? 0.58 : 0.34;
          const s = 1 - w * (0.5 - 0.5 * Math.cos(t * hz * Math.PI * 2));
          for (const g of wings) g.setAttribute("transform", `scale(${s.toFixed(3)} 1)`);
        },
        remove() { self.gone = true; e.remove(); },
      };
      return self;
    }

    // 口水。這一條不是貼圖也不是被拉長的固定形狀——每一幀重算幾何：
    //   · 連著嘴角的那一段是「掛下來的液面」，越拉越細（黏稠變細）
    //   · 中段的曲線由重力下垂 + 側向落後量決定，所以頭一動它會慢半拍甩出去
    //   · 末端是一顆會被重力拉成水滴形的珠子，越積越大
    //   · 高光有兩處：珠子上緣的亮點（球面反射）與絲上的一道細長反光
    //   · 邊緣一圈比本體深一點，那是液體邊緣的折射，少了它看起來就會像塑膠
    // 由 idle.js 每一幀餵物理狀態進來（見 _drool）。
    droolStrand() {
      const uid = "drl" + (Fx._uid = (Fx._uid || 0) + 1);
      const e = document.createElementNS(NS, "g");
      e.innerHTML =
        "<defs>" +
        // 本體橫向漸層：兩側暗、偏左有一條亮帶。液體讀起來像液體靠的就是
        // 「中間比邊緣透」＋「一側有集中反光」，不是整條同一個顏色。
        `<linearGradient id="${uid}b" x1="0" y1="0" x2="1" y2="0">` +
        '<stop offset="0" stop-color="#79b4d6" stop-opacity=".46"/>' +
        '<stop offset=".22" stop-color="#f4fcff" stop-opacity=".66"/>' +
        '<stop offset=".46" stop-color="#cfeeff" stop-opacity=".34"/>' +
        '<stop offset=".78" stop-color="#a5d6ef" stop-opacity=".44"/>' +
        '<stop offset="1" stop-color="#6ea9cd" stop-opacity=".58"/>' +
        "</linearGradient>" +
        `<radialGradient id="${uid}d" cx=".33" cy=".26" r=".88">` +
        '<stop offset="0" stop-color="#ffffff" stop-opacity=".86"/>' +
        '<stop offset=".34" stop-color="#eafaff" stop-opacity=".52"/>' +
        '<stop offset=".7" stop-color="#bde4f7" stop-opacity=".42"/>' +
        '<stop offset=".92" stop-color="#8cc6e6" stop-opacity=".62"/>' +
        '<stop offset="1" stop-color="#67a6cc" stop-opacity=".74"/>' +
        "</radialGradient>" +
        // 嘴角那一小攤「濕」：讓它看起來是從嘴裡滲出來的，而不是黏在臉上
        `<radialGradient id="${uid}w" cx=".5" cy=".4" r=".6">` +
        '<stop offset="0" stop-color="#e8f8ff" stop-opacity=".62"/>' +
        '<stop offset="1" stop-color="#a9d8ef" stop-opacity="0"/>' +
        "</radialGradient>" +
        "</defs>" +
        `<ellipse class="dWet" fill="url(#${uid}w)"/>` +
        `<path class="dBody" fill="url(#${uid}b)" stroke="#7ab6d8" stroke-opacity=".3" stroke-width=".7"/>` +
        `<ellipse class="dBead" fill="url(#${uid}d)" stroke="#74b0d2" stroke-opacity=".34" stroke-width=".8"/>` +
        '<path class="dGleam" fill="#ffffff" fill-opacity=".55"/>' +
        '<ellipse class="dHi" fill="#ffffff" fill-opacity=".85"/>' +
        '<ellipse class="dHi2" fill="#ffffff" fill-opacity=".38"/>';
      this.g.appendChild(e);
      const wet = e.querySelector(".dWet");
      const body = e.querySelector(".dBody"), bead = e.querySelector(".dBead");
      const gleam = e.querySelector(".dGleam");
      const hi = e.querySelector(".dHi"), hi2 = e.querySelector(".dHi2");

      // 把一串取樣點接成平滑曲線（走中點的二次貝茲），比直接連直線不會有折角
      const smooth = (pts) => {
        let d = `M ${pts[0][0].toFixed(2)} ${pts[0][1].toFixed(2)}`;
        for (let i = 1; i < pts.length - 1; i++) {
          const [x0, y0] = pts[i], [x1, y1] = pts[i + 1];
          d += ` Q ${x0.toFixed(2)} ${y0.toFixed(2)} ` +
            `${((x0 + x1) / 2).toFixed(2)} ${((y0 + y1) / 2).toFixed(2)}`;
        }
        const e2 = pts[pts.length - 1];
        return d + ` L ${e2[0].toFixed(2)} ${e2[1].toFixed(2)}`;
      };

      const self = {
        e, gone: false,
        // s = {x,y,rot,len,sway,bulge,r,alpha,scale}
        //   len   絲的長度        sway  末端側向偏移（頭甩出去的落後量）
        //   bulge 中段被甩出去的量  r     末端珠子半徑
        update(s) {
          if (self.gone) return;
          e.setAttribute("transform",
            `translate(${s.x.toFixed(1)},${s.y.toFixed(1)}) rotate(${(s.rot || 0).toFixed(2)}) ` +
            `scale(${(s.scale || 1).toFixed(3)})`);
          e.setAttribute("opacity", PET.clamp(s.alpha == null ? 1 : s.alpha, 0, 1).toFixed(2));
          const L = Math.max(1.5, s.len), r = Math.max(0.6, s.r);
          const bx = s.sway, bulge = s.bulge || 0;

          // 中心線是一條二次貝茲：起點在嘴角、控制點被甩出去、終點在珠子。
          // 寬度沿著它變化——嘴角最寬（液面），迅速被抽成細絲，接近末端再鼓回珠子。
          // 這個「寬 → 極細 → 鼓起來」的剖面就是黏稠液體被重力拉長的樣子；
          // 少了它，等寬的一條就只會讀成塑膠管或一條白線。
          const wTop = 3.4 * PET.clamp(1.15 - L / 200, 0.5, 1.15);
          const wThread = 0.55;
          const N = 16;
          const left = [], right = [];
          for (let i = 0; i <= N; i++) {
            const u = i / N;
            const cx = 2 * (1 - u) * u * bulge + u * u * bx;
            const cy = L * u;
            const taper = Math.pow(1 - u, 1.55);                       // 液面迅速收細
            const near = PET.smooth(PET.clamp((u - 0.66) / 0.34, 0, 1)); // 末端鼓回珠子
            const w = wTop * taper + wThread + r * 0.82 * near;
            left.push([cx - w, cy]);
            right.push([cx + w, cy]);
          }
          right.reverse();
          body.setAttribute("d", smooth(left) + " " + smooth(right).replace(/^M/, "L") + " Z");

          // 嘴角那一攤濕痕，跟著液面寬度走
          wet.setAttribute("cx", "0");
          wet.setAttribute("cy", "0.4");
          wet.setAttribute("rx", (wTop * 1.9).toFixed(2));
          wet.setAttribute("ry", (wTop * 0.85).toFixed(2));

          // 珠子：往下墜時被拉成蛋形（表面張力 vs 重力）
          const sag = PET.clamp(1 + L / 170, 1, 1.42);
          const by = L - r * (sag - 1) * 0.55;
          bead.setAttribute("cx", bx.toFixed(2));
          bead.setAttribute("cy", by.toFixed(2));
          bead.setAttribute("rx", r.toFixed(2));
          bead.setAttribute("ry", (r * sag).toFixed(2));

          // 絲上的反光：只佔上面一段、很細，而且偏左（跟漸層的亮帶同一側）。
          // 整條都打光會變成一根塑膠管上的高光條。
          const g0 = 0.12, g1 = 0.62;
          const gl = [], gr = [];
          for (let i = 0; i <= 8; i++) {
            const u = g0 + ((g1 - g0) * i) / 8;
            const cx = 2 * (1 - u) * u * bulge + u * u * bx;
            const cy = L * u;
            const taper = Math.pow(1 - u, 1.55);
            const w = wTop * taper + wThread;
            const gw = Math.max(0.16, w * 0.3);
            const off = -w * 0.34;
            gl.push([cx + off - gw, cy]);
            gr.push([cx + off + gw, cy]);
          }
          gr.reverse();
          gleam.setAttribute("d", smooth(gl) + " " + smooth(gr).replace(/^M/, "L") + " Z");

          // 珠子的球面高光（左上）＋對側一點環境反射（右下，弱很多）
          hi.setAttribute("cx", (bx - r * 0.33).toFixed(2));
          hi.setAttribute("cy", (by - r * 0.44).toFixed(2));
          hi.setAttribute("rx", (r * 0.29).toFixed(2));
          hi.setAttribute("ry", (r * 0.44).toFixed(2));
          hi.setAttribute("transform",
            `rotate(-22 ${(bx - r * 0.33).toFixed(2)} ${(by - r * 0.44).toFixed(2)})`);
          hi2.setAttribute("cx", (bx + r * 0.4).toFixed(2));
          hi2.setAttribute("cy", (by + r * 0.5).toFixed(2));
          hi2.setAttribute("rx", (r * 0.16).toFixed(2));
          hi2.setAttribute("ry", (r * 0.2).toFixed(2));
        },
        remove() { self.gone = true; e.remove(); },
      };
      return self;
    }

    clear() { for (const p of this.live) p.e.remove(); this.live.length = 0; }
  };
  const Fx = PET.Fx;
})();
