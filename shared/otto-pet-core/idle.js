// idle.js — 51 種待機行為 + 排程器
// 原有 5 種：深呼吸 / 東張西望 / 伸懶腰 / 打盹 / 玩雪
// 第二批 6 種：打呵欠 / 理毛 / 發呆 / 哼歌 / 聞聞 / 扭扭舞
// 第三批 20 種：揮手 / 探頭 / 耳朵抖抖 / 小跳 / 圍巾飄 / 數星星 /
// 看月亮 / 拍拍手 / 比心 / 平衡 / 踮腳 / 躲貓貓 / 滾雪球 / 捧暖暖 /
// 擺拍 / 點子 / 搖頭 / 小旋轉 / 得意抬頭 / 軟綿綿
//
// 本輪新增 20 種「可互動」待機：吹泡泡 / 接雪花 / 想吃魚 / 追蝴蝶 / 拍皮球 /
// 躲貓貓找你 / 許願星 / 音樂盒 / 堆雪人 / 照鏡子 / 拼圖 / 自拍 / 泡熱可可 /
// 看故事書 / 畫畫 / 放風箏 / 雪天使 / 企鵝朋友 / 溜冰 / 放天燈
//
// 「可互動」的意思是：這些待機播放時，畫面上會浮出一個可以按的小道具
// （IDLE_LIST 裡的 tap 欄位），按下去金孫會演出完全不同的收尾；
// 不理它的話就照原本的方式默默結束。所以同一個待機有兩種結局。
(function () {
  const PET = (window.PET = window.PET || {});

  // 每個行為：權重 w、中文名 zh、是否需要閒置一段時間才會出現 after、
  // tap = 可互動道具 {icon, label, x, y}（x/y 是舞台百分比位置）
  PET.IDLE_LIST = {
    breathe:  { zh: "深呼吸", w: 3 },
    look:     { zh: "東張西望", w: 3 },
    stretch:  { zh: "伸懶腰", w: 2 },
    yawn:     { zh: "打呵欠", w: 1.8 },
    groom:    { zh: "理毛", w: 1.8 },
    daydream: { zh: "發呆", w: 2 },
    hum:      { zh: "哼歌", w: 1.6 },
    sniff:    { zh: "聞聞", w: 1.6 },
    wiggle:   { zh: "扭扭舞", w: 1.2 },
    wave:     { zh: "揮手打招呼", w: 1.4 },
    peek:     { zh: "探頭探腦", w: 1.5 },
    earWiggle:{ zh: "耳朵抖抖", w: 1.3 },
    hop:      { zh: "小跳一下", w: 1.2 },
    scarf:    { zh: "圍巾飄飄", w: 1.5 },
    countStars:{ zh: "數星星", w: 1.3 },
    moonGaze: { zh: "看月亮", w: 1.5 },
    clap:     { zh: "拍拍手", w: 1.1 },
    heart:    { zh: "比一個心", w: 1.1 },
    balance:  { zh: "努力平衡", w: 1.2 },
    tiptoe:   { zh: "踮腳走路", w: 1.2 },
    peekaboo: { zh: "躲貓貓", w: 1.2 },
    snowball: { zh: "滾雪球", w: 1.2 },
    warmCup:  { zh: "捧暖暖", w: 1.2 },
    portrait: { zh: "擺拍留念", w: 1.1 },
    idea:     { zh: "冒出點子", w: 1.3 },
    nod:      { zh: "認真點頭", w: 1.4 },
    twirl:    { zh: "小小旋轉", w: 1.1 },
    proud:    { zh: "得意抬頭", w: 1.1 },
    melt:     { zh: "軟綿綿融化", w: 1.2 },

    // ---------- 20 種可互動待機 ----------
    bubble:   { zh: "吹泡泡", w: 1.5, tap: { icon: "🫧", label: "戳破泡泡", x: 68, y: 26 } },
    fishDream:{ zh: "想吃魚", w: 1.4, tap: { icon: "🐟", label: "餵他一條", x: 72, y: 34 } },
    ballPlay: { zh: "拍皮球", w: 1.4, tap: { icon: "⚽", label: "把球丟給他", x: 25, y: 46 } },
    seekYou:  { zh: "躲貓貓找你", w: 1.4, tap: { icon: "🙈", label: "我在這裡！", x: 74, y: 46 } },
    wishStar: { zh: "許願星", w: 1.3, tap: { icon: "🌟", label: "一起許願", x: 62, y: 17 } },
    musicBox: { zh: "音樂盒", w: 1.3, tap: { icon: "🎵", label: "上發條", x: 28, y: 40 } },
    snowman:  { zh: "堆雪人", w: 1.3 },
    mirror:   { zh: "照鏡子", w: 1.3, tap: { icon: "🪞", label: "舉高一點", x: 26, y: 33 } },
    puzzle:   { zh: "拼圖", w: 1.3, tap: { icon: "🧩", label: "遞最後一片", x: 71, y: 44 } },
    selfie:   { zh: "自拍", w: 1.3, tap: { icon: "📸", label: "幫他按快門", x: 35, y: 24 } },
    cocoa:    { zh: "泡熱可可", w: 1.4, tap: { icon: "☕", label: "端給他", x: 67, y: 47 } },
    storybook:{ zh: "看故事書", w: 1.4 },
    painting: { zh: "畫畫", w: 1.3, tap: { icon: "🎨", label: "看看畫了什麼", x: 73, y: 28 } },
    kite:     { zh: "放風箏", w: 1.3, tap: { icon: "🪁", label: "拉一下線", x: 24, y: 16 } },
    snowAngel:{ zh: "雪天使", w: 1.2, tap: { icon: "👼", label: "拍拍他", x: 50, y: 62 } },
    penguin:  { zh: "企鵝朋友", w: 1.3, tap: { icon: "🐧", label: "介紹一下", x: 76, y: 58 } },
    skate:    { zh: "溜冰", w: 1.3, tap: { icon: "⛸️", label: "喊聲加油", x: 22, y: 55 } },
    lantern:  { zh: "放天燈", w: 1.3, tap: { icon: "🏮", label: "一起放上去", x: 64, y: 14 } },

    // ---------- 嘴饞與小生物 ----------
    // 小生物是真的畫出來會飛的（fx_art.js 的 CRITTER），不是用星星代打。
    // 權重刻意調高（一般待機是 1.1~2）：這三種是最有看頭的，要常出來。
    // 蝴蝶原本叫「追蝴蝶」、排在第 32 個夾在拼圖自拍那一堆裡，三隻一組卻只有
    // 兩隻站在一起，看起來就像少了一隻。歸位到這裡並跟兄弟統一命名。
    drool:    { zh: "流口水嘴饞", w: 2.2, tap: { icon: "🍡", label: "餵他一口", x: 70, y: 40 } },
    bee:      { zh: "蜜蜂嗡嗡", w: 3.6, tap: { icon: "🌻", label: "給蜜蜂一朵花", x: 26, y: 22 } },
    butterfly:{ zh: "蝴蝶飛舞", w: 3.6, tap: { icon: "🦋", label: "摸摸蝴蝶", x: 30, y: 30 } },
    dragonfly:{ zh: "蜻蜓來了", w: 3.4, tap: { icon: "👆", label: "伸出手指", x: 74, y: 24 } },

    doze:     { zh: "打盹", w: 6, after: 45 },
  };

  PET.IDLE_TAPPABLE = Object.keys(PET.IDLE_LIST).filter((k) => PET.IDLE_LIST[k].tap);

  PET.Idle = class {
    constructor(pet) {
      this.pet = pet;
      pet.idle = this;
      this.suspended = false;
      this.cur = null; this.curT = 0;
      this.nextIn = 3.5;
      this.lastKey = "";
      this.sinceActivity = 0;
      this.dozeFx = 0;
      this.fxIn = 0;
      this.bias = null;
      this.critterEl = null; this.critterType = null;
      this.droolEl = null;
      this.forced = null;      // playNext 指定的下一個待機
    }

    poke() {  // 使用者活動 → 醒來
      this.sinceActivity = 0;
      if (this.cur && this.cur.key === "doze") this._end(true);
    }
    suspend() { this.suspended = true; this._end(); }
    resume() {
      this.suspended = false;
      // 有人指定了下一個就別讓它等太久，不然接不上剛剛發生的事
      this.nextIn = this.forced ? 0.8 : 2 + Math.random() * 3;
    }

    // 指定「下一次待機就演這一個」。給外部事件接一段特定反應用
    // （例如查到附近有好吃的 → 嘴饞）。用這個而不是另外寫一份動畫：
    // 口水的嘴角座標與黏稠物理只該有一份，複製一份出去遲早會走鐘。
    playNext(key) {
      if (!PET.IDLE_LIST[key]) return false;
      this.forced = key;
      if (!this.suspended && !this.cur) this.nextIn = Math.min(this.nextIn, 0.8);
      return true;
    }

    // 使用者按了浮出來的小道具：記下時間，讓 step() 切到「被陪玩」那條收尾。
    // 只認第一下，連按不會把動作切斷重演。
    tap() {
      const c = this.cur;
      if (!c || !c.tap || c.hit) return false;
      c.hit = true; c.hitT = this.curT;
      this.pet._emit("idleTap", { key: c.key, state: "done" });
      this.sinceActivity = 0;
      return true;
    }

    _end(wake) {
      // 常駐的小生物與口水不會自己消失（它們不是會過期的粒子），要在這裡收掉
      if (this.critterEl) { this.critterEl.remove(); this.critterEl = null; this.critterType = null; }
      if (this.droolEl) { this.droolEl.remove(); this.droolEl = null; }
      if (this.cur && this.cur.tap) this.pet._emit("idleTap", { key: this.cur.key, state: "end" });
      this.cur = null; this.curT = 0;
      this.nextIn = 4.5 + Math.random() * 7;
      if (wake) { // 打盹被吵醒 → 小驚訝
        const p = this.pet;
        p.faceS.eyeOpen.snap(1.25); p.faceS.eyeOpen.set(1);
        p.springs.rootY.vel -= 260;
        setTimeout(() => p.setEmotion("calm", { soft: true }), 700);
      }
    }

    // 天氣場景會偏好某些待機行為（下雪就多玩雪、大太陽就多打呵欠）
    setBias(keys) { this.bias = keys && keys.length ? new Set(keys) : null; }

    _pick() {
      if (this.forced) { const k = this.forced; this.forced = null; return k; }
      const opts = [];
      for (const [key, o] of Object.entries(PET.IDLE_LIST)) {
        if (o.after != null && this.sinceActivity <= o.after) continue;
        opts.push({ key, w: this.bias && this.bias.has(key) ? o.w * 4 : o.w });
      }
      const pool = opts.filter((o) => o.key !== this.lastKey);
      let sum = pool.reduce((s, o) => s + o.w, 0), r = Math.random() * sum;
      for (const o of pool) { r -= o.w; if (r <= 0) return o.key; }
      return "breathe";
    }

    // 只在跨過某個時間點時觸發一次
    _at(t, dt, mark) { return t >= mark && t - dt < mark; }

    // 讓臉回到中性（多數行為收尾用）
    _faceReset() {
      const f = this.pet.faceS;
      f.eyeOpen.set(1); f.eyeArc.set(0);
      f.mOpen.set(0); f.mRound.set(0.2); f.mCurve.set(0.55); f.mWide.set(0.3);
      f.pupilX.set(0); f.pupilY.set(0);
      f.browShow.set(0); f.tear.set(0);
    }

    step(dt, P) {
      this.sinceActivity += dt;
      if (this.suspended) return;

      if (!this.cur) {
        this.nextIn -= dt;
        if (this.nextIn <= 0) {
          const key = this._pick();
          this.lastKey = key;
          this.cur = { key }; this.curT = 0;
          this.fxIn = 0;
          this._enter(key);
        }
        return;
      }

      this.curT += dt;
      const t = this.curT, p = this.pet, f = p.faceS;
      switch (this.cur.key) {
        case "breathe": { // 深呼吸 + 偶發雙眨眼
          P.sy += 0.012 * Math.sin(t * Math.PI / 1.9);
          if (this._at(t, dt, 1.4)) { p.blinkPhase = 0; setTimeout(() => (p.blinkPhase = 0), 240); }
          if (t > 4.2) this._end();
          break;
        }
        case "look": { // 東張西望：視線+頭微轉
          const seq = [[0.3, -0.8, -0.1], [1.5, 0.8, -0.15], [2.7, 0.2, 0.35]];
          for (const [st, px, py] of seq) {
            if (this._at(t, dt, st)) { f.pupilX.set(px); f.pupilY.set(py); }
          }
          P.headRot += t < 1.5 ? -3 * PET.smooth(Math.min(t / 0.5, 1)) : (t < 2.7 ? 3.5 : 0);
          if (t > 3.9) { f.pupilX.set(0); f.pupilY.set(0); this._end(); }
          break;
        }
        case "stretch": { // 伸懶腰：下壓→拉高→回正，瞇眼張嘴
          let arm = 0;
          if (t < 0.5) {
            const u = PET.smooth(t / 0.5);
            P.sy += -0.05 * u; P.sx += 0.045 * u; arm = 14 * u;
          }
          else if (t < 1.4) {
            const u = PET.smooth((t - 0.5) / 0.9);
            P.sy += PET.lerp(-0.05, 0.075, u); P.sx += PET.lerp(0.045, -0.05, u);
            P.rootY -= 26 * u; P.headRot -= 5 * u; arm = PET.lerp(14, 82, u);
          } else if (t < 2.2) {
            P.sy += 0.075; P.sx += -0.05; P.rootY -= 26; P.headRot -= 5; arm = 82;
          } else if (t < 2.9) {
            const u = PET.smooth((t - 2.2) / 0.7);
            P.sy += PET.lerp(0.075, 0, u); P.sx += PET.lerp(-0.05, 0, u);
            P.rootY -= 26 * (1 - u); P.headRot -= 5 * (1 - u); arm = 82 * (1 - u);
          }
          P.armLShoulder += arm; P.armRShoulder -= arm;
          P.armLElbow += arm * 0.12; P.armRElbow -= arm * 0.12;
          if (this._at(t, dt, 0.5)) {
            f.eyeOpen.set(0.08); f.eyeArc.set(0.7); f.mOpen.set(0.75); f.mRound.set(0.7);
          }
          if (this._at(t, dt, 2.4)) {
            f.eyeOpen.set(1); f.eyeArc.set(0);
            f.mOpen.set(0); f.mRound.set(0.2); f.mCurve.set(0.55);
          }
          if (t > 3.3) this._end();
          break;
        }
        case "doze": { // 打盹：點頭+Zzz，直到被吵醒
          P.headRot += 2 + Math.sin(t * 0.9) * 2.5;
          P.headY += 18 + Math.sin(t * 0.9) * 8;
          P.sy += -0.018;
          if (this._at(t, dt, 0.3)) {
            f.eyeOpen.set(0.05); f.eyeArc.set(0.05);
            f.mOpen.set(0); f.mCurve.set(0.2);
          }
          this.dozeFx -= dt;
          if (this.dozeFx <= 0) {
            this.dozeFx = 2.4;
            p.fx.spawn("zzz", { x: 1000, y: 215, vy: -44, vx: 24, life: 2.3 });
          }
          // 不自動結束；poke() 吵醒
          if (t > 40) this._end();
          break;
        }
        // 「玩雪」與「接雪花」已移除：待機時不再自己下起雪來。
        // 下雪只有在查詢天氣、而且那邊真的在下雪時才會出現（見 scene.js）。

        // ---------- 以下為新增 6 種 ----------

        case "yawn": { // 打呵欠：吸氣抬頭→嘴張到最大→洩氣低頭，眼角擠出一點淚
          if (t < 0.55) {              // 吸氣，身體長高、頭微抬
            const u = PET.smooth(t / 0.55);
            P.sy += 0.045 * u; P.rootY -= 10 * u; P.headY -= 8 * u; P.headRot -= 2 * u;
          } else if (t < 1.7) {        // 呵欠張到最大並定住
            P.sy += 0.045; P.rootY -= 10; P.headY -= 8; P.headRot -= 2;
          } else if (t < 2.6) {        // 洩氣
            const u = PET.smooth((t - 1.7) / 0.9);
            P.sy += PET.lerp(0.045, -0.05, u);
            P.sx += 0.04 * u;
            P.rootY += PET.lerp(-10, 9, u);
            P.headY += PET.lerp(-8, 16, u);
            P.headRot += PET.lerp(-2, 2, u);
          } else {
            P.sy += -0.03; P.sx += 0.025; P.rootY += 5; P.headY += 10;
          }
          if (this._at(t, dt, 0.5)) {  // 嘴慢慢張開、眼睛擠起來
            f.eyeOpen.set(0.05); f.eyeArc.set(-0.6);
            f.mOpen.set(0.95); f.mRound.set(0.95); f.mWide.set(0.15); f.mCurve.set(-0.2);
            f.browShow.set(0.7); f.browTilt.set(-0.5);
          }
          // （原本這裡打呵欠會逼出一滴生理性的眼淚。依使用者要求，待機一律
          //   不出現眼淚——在螢幕上它讀起來就是在哭，跟打呵欠的本意相反。）
          if (this._at(t, dt, 1.9)) { // 收嘴
            f.mOpen.set(0.1); f.mRound.set(0.4); f.mCurve.set(0.2);
            f.eyeOpen.set(0.25); f.eyeArc.set(0.2); f.browShow.set(0);
          }
          if (this._at(t, dt, 2.9)) { this._faceReset(); }
          if (t > 3.6) this._end();
          break;
        }

        case "groom": { // 理毛：歪頭把耳朵送到手邊，快速搔幾下，舒服得瞇眼
          // 側邊在這裡惰性決定，外部直接塞 idle.cur={key:'groom'} 也不會拿到 undefined
          if (!this.cur.side) this.cur.side = Math.random() < 0.5 ? -1 : 1;
          const side = this.cur.side;
          if (t < 0.4) {
            const u = PET.smooth(t / 0.4);
            P.headRot += 4.5 * side * u; P.headY += 5 * u;
          } else if (t < 2.5) {        // 搔癢：頭與手同頻抖
            const buzz = Math.sin(t * 34);
            P.headRot += 4.5 * side + buzz * 1.6;
            P.headY += 5 + Math.sin(t * 30) * 2.5;
            P.headX += buzz * 2.2 * side;
            const arm = 62 + buzz * 12;
            if (side < 0) { P.armLShoulder += arm; P.armLElbow += arm * 0.35; }
            else { P.armRShoulder -= arm; P.armRElbow -= arm * 0.35; }
            this.fxIn -= dt;
            if (this.fxIn <= 0) {
              this.fxIn = 0.5;
              p.fx.spawn("sparkle", {
                x: side < 0 ? 565 : 985, y: 255,
                vx: side * 14, life: 0.85, s0: 0.3, s1: 0.85,
              });
            }
          } else if (t < 3.1) {
            const u = 1 - PET.smooth((t - 2.5) / 0.6);
            P.headRot += 4.5 * side * u; P.headY += 5 * u;
            const arm = 62 * u;
            if (side < 0) { P.armLShoulder += arm; P.armLElbow += arm * 0.35; }
            else { P.armRShoulder -= arm; P.armRElbow -= arm * 0.35; }
          }
          if (this._at(t, dt, 0.45)) {
            f.eyeOpen.set(0.08); f.eyeArc.set(1);
            f.mCurve.set(0.85); f.mWide.set(0.5); f.blush.set(1.1);
          }
          if (this._at(t, dt, 2.6)) { this._faceReset(); f.blush.set(0.75); }
          if (t > 3.4) this._end();
          break;
        }

        case "daydream": { // 發呆：視線慢慢飄、頭緩緩歪（不再冒思緒點點，那會蓋在臉上）
          const u = Math.min(1, t / 0.8);
          f.eyeOpen.set(PET.lerp(1, 0.45, u));
          f.pupilX.set(-0.45 + Math.sin(t * 0.55) * 0.25);
          f.pupilY.set(-0.5 + Math.sin(t * 0.4 + 1) * 0.18);
          f.mCurve.set(0.15); f.mWide.set(0.18);
          P.headRot += Math.sin(t * 0.42) * 3.2;
          P.headY += 6 + Math.sin(t * 0.6) * 3;
          P.sy += -0.012;
          if (t > 5.6) { this._faceReset(); this._end(); }
          break;
        }

        case "hum": { // 哼歌：身體打拍子，嘴一開一合，♪ 飄出來
          const beat = t * 2.1;                       // 約 126 BPM
          P.rootRot += Math.sin(beat * Math.PI) * 2.4;
          P.rootY -= Math.abs(Math.sin(beat * Math.PI)) * 7;
          P.headRot += Math.sin(beat * Math.PI + 0.6) * 2.6;
          P.armLShoulder += Math.sin(beat * Math.PI) * 9;
          P.armRShoulder += Math.sin(beat * Math.PI) * 9;
          // 每拍換一次嘴型，像在哼旋律
          const phase = Math.floor(beat) % 2;
          f.mOpen.set(phase ? 0.32 : 0.1);
          f.mRound.set(phase ? 0.85 : 0.4);
          f.mWide.set(0.2);
          if (this._at(t, dt, 0.15)) { f.eyeOpen.set(0.1); f.eyeArc.set(1); f.blush.set(1); }
          this.fxIn -= dt;
          if (this.fxIn <= 0) {
            this.fxIn = 0.95;
            p.fx.spawn("note", {
              x: 990 + Math.random() * 40, y: 240,
              vy: -52, vx: 16, life: 1.6, s1: 1.15, spin: 40,
            });
          }
          if (t > 5.2) { this._faceReset(); f.blush.set(0.75); this._end(); }
          break;
        }

        case "sniff": { // 聞聞：頭往前下方湊近，鼻子快速抽動幾下
          if (t < 0.5) {
            const u = PET.smooth(t / 0.5);
            P.headY += 16 * u; P.headRot += 2 * u; P.sy += -0.025 * u;
          } else if (t < 2.4) {
            P.headY += 16 + Math.sin(t * 26) * 3.5;   // 抽鼻子
            P.headRot += 2 + Math.sin(t * 13) * 1.4;
            P.sy += -0.025;
            f.pupilY.set(0.55); f.pupilX.set(Math.sin(t * 1.6) * 0.3);
          } else if (t < 3.0) {
            const u = 1 - PET.smooth((t - 2.4) / 0.6);
            P.headY += 16 * u; P.headRot += 2 * u;
          }
          if (this._at(t, dt, 0.45)) {
            f.eyeOpen.set(0.42); f.mOpen.set(0.1); f.mRound.set(0.7); f.mWide.set(0.12);
          }
          if (this._at(t, dt, 2.45)) {                // 聞到好東西 → 眼睛一亮
            f.eyeOpen.set(1.2); f.pupilScale.set(1.15); f.pupilX.set(0); f.pupilY.set(0);
            f.mCurve.set(0.8); f.mWide.set(0.45); f.mOpen.set(0); f.blush.set(1.05);
            p.fx.spawn("sparkle", { x: 990, y: 250, life: 1.1, s1: 1.15 });
          }
          if (this._at(t, dt, 3.4)) { this._faceReset(); f.pupilScale.set(1); f.blush.set(0.75); }
          if (t > 4.0) this._end();
          break;
        }

        case "wiggle": { // 扭扭舞：左右扭腰 + 踏步 + 手擺動
          const beat = t * 2.6;
          const s = Math.sin(beat * Math.PI);
          P.rootRot += s * 3.2;
          P.rootX += Math.sin(beat * Math.PI) * 9;
          P.rootY -= Math.abs(Math.sin(beat * Math.PI)) * 12;
          P.sx += Math.sin(beat * Math.PI * 2) * 0.02;
          P.sy -= Math.sin(beat * Math.PI * 2) * 0.02;
          P.headRot += Math.sin(beat * Math.PI + 1.1) * 3;
          P.armLShoulder += s * 26; P.armRShoulder += s * 26;
          P.armLElbow += s * 8; P.armRElbow += s * 8;
          P.legLRot += s * 5; P.legRRot += s * 5;
          if (this._at(t, dt, 0.1)) {
            f.eyeOpen.set(0.1); f.eyeArc.set(1);
            f.mOpen.set(0.35); f.mWide.set(0.8); f.mCurve.set(0.9); f.blush.set(1.15);
          }
          this.fxIn -= dt;
          if (this.fxIn <= 0) {
            this.fxIn = 1.2;
            p.fx.spawn("note", { x: 560 + Math.random() * 460, y: 300, vy: -46, life: 1.5, s1: 1.1 });
          }
          if (t > 4.4) { this._faceReset(); f.blush.set(0.75); this._end(); }
          break;
        }

        case "wave": { // 揮手打招呼：左右輕晃，讓臉保持親切
          P.rootX += Math.sin(t * 2.5) * 8; P.headRot += Math.sin(t * 2.5 + 0.8) * 2.8;
          P.scarfRot += Math.sin(t * 2.5 + 1) * 3;
          if (this._at(t, dt, 0.25)) { f.eyeOpen.set(1.1); f.mCurve.set(0.8); f.blush.set(1); }
          if (t > 3.6) { this._faceReset(); f.blush.set(0.75); this._end(); }
          break;
        }
        case "peek": { // 探頭探腦：左右看看再探回來
          const side = Math.sin(t * 1.5);
          P.headX += side * 16; P.headRot += side * 4; P.rootX += side * 5;
          f.pupilX.set(PET.clamp(side * 0.8, -1, 1)); f.pupilY.set(-0.1);
          if (t > 4.2) { this._faceReset(); this._end(); }
          break;
        }
        case "earWiggle": { // 耳朵抖抖：用快速頭部微震與眼睛眨動表現耳朵彈性
          P.headRot += Math.sin(t * 18) * 2.2; P.headY += Math.sin(t * 18 + 1) * 2;
          P.scarfRot += Math.sin(t * 9) * 2.2;
          if (this._at(t, dt, 0.35) || this._at(t, dt, 1.2)) p.blinkPhase = 0;
          if (t > 2.6) this._end();
          break;
        }
        case "hop": { // 小跳一下：彈簧負責落地，圍巾有延遲晃動
          P.sy += Math.sin(t * 3.6) * 0.035; P.rootY -= Math.max(0, Math.sin(t * 3.6)) * 18;
          P.headY += Math.sin(t * 3.6 + 0.5) * 4; P.scarfRot += Math.sin(t * 3.6 + 1.2) * 5;
          if (this._at(t, dt, 0.24) || this._at(t, dt, 1.3)) p.springs.rootY.vel -= 180;
          if (t > 2.4) this._end();
          break;
        }
        case "scarf": { // 圍巾飄飄：讓新布料尾端成為主角
          P.scarfRot += 7 + Math.sin(t * 1.7) * 6; P.headRot += Math.sin(t * 1.1) * 1.8;
          P.rootRot += Math.sin(t * 1.7) * 0.7; P.rootY -= Math.abs(Math.sin(t * 1.7)) * 3;
          if (t > 5.2) this._end();
          break;
        }
        case "countStars": { // 數星星：眼睛依序追三個高光
          const phase = Math.floor(t / 0.85) % 3;
          const eyes = [[-0.65, -0.55], [0.05, -0.8], [0.7, -0.45]][phase];
          f.pupilX.set(eyes[0]); f.pupilY.set(eyes[1]); P.headRot += eyes[0] * 2.2;
          this.fxIn -= dt;
          if (this.fxIn <= 0) { this.fxIn = 1.1; p.fx.spawn("sparkle", { x: 660 + phase * 120, y: 170, life: 1.1, s1: 1.2 }); }
          if (t > 3.4) { this._faceReset(); this._end(); }
          break;
        }
        case "moonGaze": { // 看月亮：慢慢抬頭，眼神留在上方
          P.headY -= 10 + Math.sin(t * 0.75) * 3; P.headRot += Math.sin(t * 0.7) * 2;
          f.pupilY.set(-0.72); f.pupilX.set(Math.sin(t * 0.6) * 0.18); f.eyeOpen.set(0.9);
          if (t > 4.8) { this._faceReset(); this._end(); }
          break;
        }
        case "clap": { // 拍拍手：身體上下拍節奏，臉頰微紅
          const beat = Math.sin(t * 7.2);
          P.rootY -= Math.max(0, beat) * 8; P.rootRot += beat * 1.4; P.headRot += beat * 2.2;
          f.mOpen.set(beat > 0 ? 0.28 : 0.08); f.mRound.set(beat > 0 ? 0.75 : 0.35);
          if (t > 3.8) { this._faceReset(); this._end(); }
          break;
        }
        case "heart": { // 比心：胸口靠近、心形浮出
          const u = PET.smooth(Math.min(1, t / 0.65));
          P.rootY -= 10 * u; P.headY += 4 * u; P.headRot += Math.sin(t * 1.6) * 1.5;
          f.eyeOpen.set(0.35); f.eyeArc.set(0.9); f.mCurve.set(0.9); f.blush.set(1.2);
          this.fxIn -= dt;
          if (this.fxIn <= 0) { this.fxIn = 1.2; p.fx.spawn("heart", { x: 774, y: 420, vy: -28, life: 1.5, s1: 1.15 }); }
          if (t > 3.5) { this._faceReset(); f.blush.set(0.75); this._end(); }
          break;
        }
        case "balance": { // 努力平衡：左右擺動後穩住
          const sway = Math.sin(t * 1.9) * (t < 2.2 ? 5.5 : 2.2);
          P.rootRot += sway; P.headRot -= sway * 0.65; P.rootX += sway * 1.8; P.scarfRot -= sway * 1.4;
          f.pupilX.set(PET.clamp(-sway / 6, -1, 1));
          if (t > 4.1) { this._faceReset(); this._end(); }
          break;
        }
        case "tiptoe": { // 踮腳走路：身體拉高、步伐輕盈
          const step = Math.sin(t * 4.4);
          P.sy += 0.035 + Math.max(0, step) * 0.018; P.rootY -= 12 + Math.max(0, step) * 8;
          P.rootX += step * 7; P.headRot += step * 2.2; P.scarfRot += step * 3;
          if (t > 3.8) this._end();
          break;
        }
        case "peekaboo": { // 躲貓貓：整隻左右縮進再探出
          const u = Math.sin(t * 1.35);
          P.rootX += u * 22; P.headX += u * 14; P.headRot += u * 4.5; P.sx -= Math.abs(u) * 0.025;
          f.eyeOpen.set(0.85 + Math.abs(u) * 0.3); f.pupilX.set(-u * 0.45);
          if (t > 4.5) { this._faceReset(); this._end(); }
          break;
        }
        case "snowball": { // 滾雪球：向下看著一顆越滾越大的光球
          const roll = Math.min(1.4, t * 0.28);
          P.headY += 18; P.headRot += Math.sin(t * 1.6) * 2; P.rootX += Math.sin(t * 1.6) * 8;
          f.pupilY.set(0.65); f.pupilX.set(Math.sin(t * 1.6) * 0.4);
          this.fxIn -= dt;
          if (this.fxIn <= 0) { this.fxIn = 1.1; p.fx.spawn("sparkle", { x: 700 + t * 30, y: 620, life: 1.2, s0: 0.5, s1: 0.9 + roll }); }
          if (t > 4.2) { this._faceReset(); this._end(); }
          break;
        }
        case "warmCup": { // 捧暖暖：縮起肩膀，舒服地吹一口氣
          P.sy -= 0.02; P.rootY += 8; P.headY += 9; P.headRot += 1.8 + Math.sin(t * 0.8) * 1.2;
          f.eyeOpen.set(0.3); f.eyeArc.set(0.6); f.mCurve.set(0.6); f.mOpen.set(t % 1.5 < 0.25 ? 0.35 : 0.08);
          if (t > 4.2) { this._faceReset(); this._end(); }
          break;
        }
        case "portrait": { // 擺拍留念：定格兩次再輕輕眨眼
          const pose = Math.sin(t * 2.1) > 0 ? 1 : -1;
          P.headRot += pose * 3.5; P.headX += pose * 6; P.rootY -= 4;
          f.pupilX.set(pose * 0.25); f.eyeOpen.set(1.08); f.mCurve.set(0.82); f.blush.set(0.95);
          if (this._at(t, dt, 1.05) || this._at(t, dt, 2.45)) p.fx.spawn("sparkle", { x: 774 + pose * 70, y: 260, life: 0.9, s1: 1.15 });
          if (t > 3.4) { this._faceReset(); f.blush.set(0.75); this._end(); }
          break;
        }
        case "idea": { // 冒出點子：先困惑，再亮起來
          P.headRot += Math.sin(t * 1.3) * 3; P.headY += 5;
          if (this._at(t, dt, 0.25)) { f.browShow.set(0.8); f.mCurve.set(0.1); f.pupilY.set(-0.4); }
          if (this._at(t, dt, 1.3)) { f.browShow.set(0); f.mCurve.set(0.8); f.eyeOpen.set(1.15); p.fx.spawn("sparkle", { x: 1010, y: 190, life: 1.4, s1: 1.4 }); }
          if (t > 3.3) { this._faceReset(); this._end(); }
          break;
        }
        case "nod": { // 認真點頭：三次小幅確認
          P.headY += Math.abs(Math.sin(t * 4.2)) * 10; P.headRot += Math.sin(t * 4.2) * 1.5;
          f.eyeOpen.set(0.92); f.mCurve.set(0.55);
          if (t > 3.2) { this._faceReset(); this._end(); }
          break;
        }
        case "twirl": { // 小小旋轉：全身慢轉，圍巾因慣性多晃半拍
          P.rootRot += Math.sin(t * 1.45) * 5; P.headRot += Math.sin(t * 1.45 + 0.8) * 3;
          P.scarfRot += Math.sin(t * 1.45 + 1.3) * 7; P.rootY -= Math.abs(Math.sin(t * 1.45)) * 6;
          if (t > 4.2) this._end();
          break;
        }
        case "proud": { // 得意抬頭：胸口挺起、看向遠方
          P.sy += 0.025; P.rootY -= 8; P.headY -= 10; P.headRot -= 2.5;
          f.eyeOpen.set(1.08); f.pupilY.set(-0.5); f.mCurve.set(0.75); f.blush.set(0.9);
          if (t > 3.8) { this._faceReset(); f.blush.set(0.75); this._end(); }
          break;
        }
        case "melt": { // 軟綿綿融化：縮下去再彈回，像毛毯一樣柔軟
          const u = Math.sin(Math.min(Math.PI, t * 1.5));
          P.sy -= u * 0.06; P.sx += u * 0.05; P.rootY += u * 18; P.headY += u * 14;
          P.headRot += Math.sin(t * 1.25) * 2; P.scarfRot += Math.sin(t * 1.25 + 1) * 4;
          f.eyeOpen.set(1 - u * 0.75); f.mCurve.set(0.3 + u * 0.35);
          if (t > 3.2) { this._faceReset(); this._end(); }
          break;
        }

        // ================= 20 種可互動待機 =================
        // H < 0 表示還沒被按（等待段）；H >= 0 是按下之後經過的秒數（收尾段）。
        // 每一支都有「有人陪玩」與「沒人理」兩種結局。

        case "bubble": { // 吹泡泡：撅嘴吹，泡泡一顆顆浮上去
          const H = this._tapT(t);
          if (H < 0) {
            P.headY += 4 + Math.sin(t * 1.3) * 2; P.headRot += Math.sin(t * 0.7) * 1.6;
            P.sy += Math.sin(t * 2.4) * 0.008;
            f.mOpen.set(0.3); f.mRound.set(1); f.mWide.set(0.1); f.eyeOpen.set(0.85);
            this.fxIn -= dt;
            if (this.fxIn <= 0) {
              this.fxIn = 0.8;
              p.fx.spawn("sparkle", { x: 1010, y: 470, vy: -58, vx: 22, life: 1.9, s0: 0.3, s1: 0.9, sway: 20 });
            }
            if (t > 6.6) { this._faceReset(); this._end(); }
          } else {                                  // 被戳破 → 嚇一跳再笑出來
            if (H < 0.35) {
              P.rootY -= 12; P.headY -= 6; P.sy += 0.03;
              f.eyeOpen.set(1.3); f.mOpen.set(0.6); f.mRound.set(0.9); f.browShow.set(0.7);
              if (this._at(H, dt, 0.02)) p.fx.spawn("bang", { x: 1010, y: 430, life: 0.7 });
            } else {
              P.rootRot += Math.sin(H * 9) * 2.4; P.headRot += Math.sin(H * 9 + 1) * 2;
              f.eyeOpen.set(0.1); f.eyeArc.set(1); f.browShow.set(0);
              f.mOpen.set(0.4); f.mWide.set(0.85); f.mCurve.set(0.95); f.blush.set(1.2);
            }
            if (H > 2) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }


        case "fishDream": { // 想吃魚：舔嘴、望著空中的魚流口水
          const H = this._tapT(t);
          if (H < 0) {
            P.headRot += 3 + Math.sin(t * 0.9) * 1.6; P.headY -= 4;
            f.pupilX.set(0.6); f.pupilY.set(-0.45); f.eyeOpen.set(1.05);
            f.mOpen.set(0.2 + Math.abs(Math.sin(t * 1.6)) * 0.18); f.mRound.set(0.5); f.mCurve.set(0.7);
            this.fxIn -= dt;
            // 這一滴是口水不是眼淚，所以用 drip（寫實的水珠）而不是 drop（淚滴符號）。
            // 淚滴符號掛在臉下方，看起來就是在哭。
            if (this.fxIn <= 0) { this.fxIn = 1.6; p.fx.spawn("drip", { x: 800, y: 500, vy: 70, vx: 0, life: 0.9, gravity: 260, s0: 0.42, s1: 0.42, sway: 0, swayHz: 0 }); }
            if (t > 6.4) { this._faceReset(); this._end(); }
          } else {                                  // 有人餵 → 撲上去接住，滿足
            if (H < 0.5) {
              P.rootY -= 30 * Math.sin(H / 0.5 * Math.PI); P.headY -= 12; P.sy += 0.04;
              P.armLShoulder += 34; P.armRShoulder -= 34;
              f.mOpen.set(0.9); f.mRound.set(0.6); f.eyeOpen.set(1.25);
            } else {
              P.headY += 6; P.sy -= 0.015;
              f.eyeOpen.set(0.08); f.eyeArc.set(1); f.mOpen.set(0.12);
              f.mCurve.set(0.9); f.mWide.set(0.5); f.blush.set(1.3);
              if (this._at(H, dt, 0.6)) p.fx.spawn("heart", { x: 900, y: 380, life: 1.6, s1: 1.4 });
            }
            if (H > 2.3) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "butterfly": { // 追蝴蝶：頭跟著繞圈的蝴蝶轉
          // 以前這裡只用星星代打，看不到蝴蝶；現在放真的會拍翅膀的那一隻。
          const H = this._tapT(t);
          const c = this._critter(p, "bfly");
          if (H < 0) {
            const a = t * 1.05;
            // 蝴蝶不會直線飛，飄忽是它的特徵：主圓周上再疊兩層不同頻率的起伏。
            // 範圍拉到幾乎整個舞台（x 320..1228），才像在畫面裡飛而不是繞著熊轉。
            const cx = 774 + Math.sin(a) * 420 + Math.sin(t * 0.61) * 55;
            const cy = 350 + Math.cos(a * 1.3) * 330 + Math.sin(t * 2.6) * 38;
            c.at(cx, cy, Math.cos(a) * 30, 3.4, t, 1);
            P.headRot += Math.sin(a) * 5; P.headX += Math.sin(a) * 14;
            P.headY += Math.cos(a * 1.3) * 9;
            this._watch(f, cx, cy);
            f.eyeOpen.set(1.12); f.mOpen.set(0.1); f.mRound.set(0.6);
            if (t > 9) { this._faceReset(); this._end(); }
          } else {                                  // 有人摸到蝴蝶 → 停在他鼻子上，屏住呼吸
            const u = PET.smooth(Math.min(1, H / 0.9));
            c.at(PET.lerp(1060, 792, u), PET.lerp(240, 402, u), PET.lerp(20, 0, u), 3.4, t, 1);
            P.headY += 2; P.sy -= 0.01 + Math.sin(H * 1.2) * 0.004;
            f.pupilX.set(0); f.pupilY.set(0.75); f.eyeOpen.set(1.2); f.pupilScale.set(1.1);
            f.mOpen.set(0); f.mCurve.set(0.5); f.mWide.set(0.18); f.blush.set(1.15);
            if (this._at(H, dt, 1.1) || this._at(H, dt, 1.9)) p.fx.spawn("sparkle", { x: 880, y: 330, life: 1.1, s1: 1 });
            if (H > 2.6) { this._faceReset(); f.pupilScale.set(1); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "ballPlay": { // 拍皮球：一下一下拍，眼睛跟著彈
          const H = this._tapT(t);
          if (H < 0) {
            const b = Math.abs(Math.sin(t * 3.1));
            P.armRShoulder -= 26 + b * 14; P.armRElbow -= 10 + b * 8;
            P.rootY -= b * 5; P.headY += 6 - b * 6;
            f.pupilY.set(0.6 - b * 0.5); f.eyeOpen.set(1.05); f.mCurve.set(0.7);
            if (t > 6.2) { this._faceReset(); this._end(); }
          } else {                                  // 有人把球丟過來 → 用頭頂一下，得意
            if (H < 0.6) {
              P.rootY -= 22 * Math.sin(H / 0.6 * Math.PI); P.headY -= 16; P.headRot -= 3;
              f.eyeOpen.set(1.25); f.mOpen.set(0.55); f.mWide.set(0.6);
              if (this._at(H, dt, 0.28)) p.fx.spawn("bang", { x: 800, y: 150, life: 0.7, s1: 1.1 });
            } else {
              P.sy += 0.028; P.rootY -= 6; P.headY -= 8; P.headRot -= 2;
              f.eyeOpen.set(0.12); f.eyeArc.set(1); f.mCurve.set(0.9); f.mWide.set(0.5); f.blush.set(1.1);
            }
            if (H > 2.2) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "seekYou": { // 躲貓貓找你：摀著眼睛數數，然後偷看
          const H = this._tapT(t);
          if (H < 0) {
            P.armLShoulder += 46; P.armRShoulder -= 46;
            P.armLElbow += 26; P.armRElbow -= 26;
            P.headY += 4; P.headRot += Math.sin(t * 1.7) * 2.2;
            const peek = t % 2.4 > 2.0;              // 每兩秒偷看一下
            f.eyeOpen.set(peek ? 0.9 : 0.05); f.eyeArc.set(peek ? 0 : 0.3);
            f.pupilX.set(peek ? 0.7 : 0);
            f.mOpen.set(0.2); f.mRound.set(0.5); f.mCurve.set(0.6);
            if (t > 7) { this._faceReset(); this._end(); }
          } else {                                  // 你出聲了 → 手放下，眼睛一亮
            P.armLShoulder += Math.max(0, 46 - H * 70); P.armRShoulder -= Math.max(0, 46 - H * 70);
            P.rootY -= Math.abs(Math.sin(H * 6)) * 10; P.headRot += Math.sin(H * 5) * 3;
            f.eyeOpen.set(1.3); f.pupilScale.set(1.12); f.pupilX.set(0);
            f.mOpen.set(0.45); f.mWide.set(0.8); f.mCurve.set(0.95); f.blush.set(1.2);
            if (this._at(H, dt, 0.1)) p.fx.spawn("sparkle", { x: 1000, y: 250, life: 1.2, s1: 1.3 });
            if (H > 2.2) { this._faceReset(); f.pupilScale.set(1); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "wishStar": { // 許願星：仰頭看著一顆特別亮的星星
          const H = this._tapT(t);
          if (H < 0) {
            P.headY -= 12 + Math.sin(t * 0.6) * 3; P.headRot += Math.sin(t * 0.5) * 1.4;
            f.pupilY.set(-0.8); f.pupilX.set(0.25); f.eyeOpen.set(1.08); f.pupilScale.set(1.08);
            f.mCurve.set(0.55); f.mWide.set(0.2);
            this.fxIn -= dt;
            if (this.fxIn <= 0) { this.fxIn = 1.5; p.fx.spawn("sparkle", { x: 940, y: 130, life: 1.4, s1: 1.25 }); }
            if (t > 6.6) { this._faceReset(); f.pupilScale.set(1); this._end(); }
          } else {                                  // 一起許願 → 閉眼合掌
            P.armLShoulder += 22; P.armRShoulder -= 22;
            P.armLElbow += 22; P.armRElbow -= 22;
            P.headY += 3; P.sy -= 0.008;
            f.eyeOpen.set(0.05); f.eyeArc.set(0.75); f.pupilScale.set(1);
            f.mCurve.set(0.7); f.mWide.set(0.22); f.blush.set(1.15);
            if (this._at(H, dt, 0.9)) {
              p.fx.spawn("sparkle", { x: 790, y: 300, life: 1.6, s1: 1.5 });
              p.fx.spawn("heart", { x: 880, y: 340, life: 1.6, s1: 1.2 });
            }
            if (H > 2.8) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "musicBox": { // 音樂盒：側耳聽著越來越慢的音樂
          const H = this._tapT(t);
          if (H < 0) {
            const slow = Math.max(0.25, 1 - t * 0.12);   // 發條沒力，節奏越來越慢
            P.headRot += 4 + Math.sin(t * 2.2 * slow) * 2.2;
            P.rootRot += Math.sin(t * 2.2 * slow) * 1.4;
            f.eyeOpen.set(0.55); f.pupilX.set(-0.35); f.mCurve.set(0.5);
            this.fxIn -= dt;
            if (this.fxIn <= 0) { this.fxIn = 1.1 / slow; p.fx.spawn("note", { x: 580, y: 380, vy: -44, vx: -12, life: 1.5 }); }
            if (t > 6.4) { this._faceReset(); this._end(); }
          } else {                                  // 上了發條 → 節奏回來，跟著搖擺
            const b = H * 2.6;
            P.rootRot += Math.sin(b * Math.PI) * 3.4; P.rootX += Math.sin(b * Math.PI) * 8;
            P.rootY -= Math.abs(Math.sin(b * Math.PI)) * 9;
            P.headRot += Math.sin(b * Math.PI + 1) * 3;
            P.armLShoulder += Math.sin(b * Math.PI) * 22; P.armRShoulder += Math.sin(b * Math.PI) * 22;
            f.eyeOpen.set(0.12); f.eyeArc.set(1); f.mOpen.set(0.3); f.mWide.set(0.7);
            f.mCurve.set(0.9); f.blush.set(1.15);
            this.fxIn -= dt;
            if (this.fxIn <= 0) { this.fxIn = 0.55; p.fx.spawn("note", { x: 560 + Math.random() * 460, y: 330, vy: -52, life: 1.4, spin: 30 }); }
            if (H > 3.2) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "snowman": { // 堆雪人：蹲著把雪拍緊（「給他紅蘿蔔」互動已移除）
          P.sy -= 0.045; P.rootY += 16; P.headY += 14;
          P.armLShoulder += 30 + Math.sin(t * 6) * 10; P.armRShoulder -= 30 + Math.sin(t * 6) * 10;
          P.armLElbow += 20; P.armRElbow -= 20;
          f.pupilY.set(0.7); f.eyeOpen.set(0.8); f.mCurve.set(0.6); f.mWide.set(0.3);
          if (t > 6.2) { this._faceReset(); this._end(); }
          break;
        }

        case "mirror": { // 照鏡子：左看右看，整理一下帽子
          const H = this._tapT(t);
          if (H < 0) {
            const s = Math.sin(t * 1.05);
            P.headRot += s * 4.5; P.headX += s * 9;
            P.armLShoulder += 34 + Math.sin(t * 2.4) * 6; P.armLElbow += 20;
            f.pupilX.set(-0.5 + s * 0.25); f.eyeOpen.set(1.05); f.mCurve.set(0.45); f.mWide.set(0.25);
            if (t > 6.4) { this._faceReset(); this._end(); }
          } else {                                  // 鏡子舉高 → 看清楚了，害羞地笑
            P.headY -= 6; P.headRot += Math.sin(H * 1.6) * 2;
            f.eyeOpen.set(0.18); f.eyeArc.set(0.95); f.pupilX.set(0);
            f.mCurve.set(0.88); f.mWide.set(0.42); f.blush.set(1.45);
            if (this._at(H, dt, 0.5)) p.fx.spawn("sparkle", { x: 630, y: 330, life: 1.2, s1: 1.2 });
            if (H > 2.4) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "puzzle": { // 拼圖：低頭研究，眉頭皺起來
          const H = this._tapT(t);
          if (H < 0) {
            P.headY += 15; P.headRot += Math.sin(t * 0.85) * 3.5;
            P.armLShoulder += 24; P.armLElbow += 18;
            f.pupilY.set(0.7); f.pupilX.set(Math.sin(t * 0.9) * 0.35);
            f.eyeOpen.set(0.7); f.browShow.set(0.7); f.browTilt.set(0.25);
            f.mCurve.set(0.05); f.mWide.set(0.2);
            // 原本這裡會冒問號，但它落在頭的右半邊、直接蓋在臉上。
            // 「想不出來」用眉毛與視線演就夠了，不需要在臉上壓一個符號。
            if (t > 6.6) { this._faceReset(); this._end(); }
          } else {                                  // 拿到最後一片 → 拼上，得意
            if (H < 0.6) {
              P.headY += 10; P.armRShoulder -= 40; P.armRElbow -= 26; P.handRFlex += 0.08;
              f.browShow.set(0.4);
            } else {
              P.sy += 0.03; P.rootY -= 10; P.headY -= 8; P.headRot -= 2.5;
              f.browShow.set(0); f.eyeOpen.set(1.2); f.pupilY.set(-0.2);
              f.mOpen.set(0.4); f.mWide.set(0.8); f.mCurve.set(0.95); f.blush.set(1.1);
              if (this._at(H, dt, 0.65)) p.fx.spawn("sparkle", { x: 1010, y: 200, life: 1.5, s1: 1.5 });
            }
            if (H > 2.4) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "selfie": { // 自拍：舉著手機喬角度
          const H = this._tapT(t);
          if (H < 0) {
            const s = Math.sin(t * 1.3);
            P.armLShoulder += 52; P.armLElbow += 26;
            P.headRot += s * 3.2; P.headX += s * 5; P.headY -= 4;
            f.pupilX.set(-0.35); f.pupilY.set(-0.3); f.eyeOpen.set(1.08);
            f.mCurve.set(0.75); f.mWide.set(0.4);
            if (t > 6.2) { this._faceReset(); this._end(); }
          } else {                                  // 有人按快門 → 閃光燈，定格笑容
            if (H < 0.25) {
              f.eyeOpen.set(0.02); f.eyeArc.set(-0.4);
              if (this._at(H, dt, 0.02)) p.fx.spawn("sparkle", { x: 660, y: 260, life: 0.7, s0: 0.8, s1: 2.4 });
            } else {
              P.armLShoulder += Math.max(0, 52 - (H - 0.25) * 90);
              P.headRot += Math.sin(H * 3) * 2;
              f.eyeOpen.set(0.15); f.eyeArc.set(1);
              f.mOpen.set(0.35); f.mWide.set(0.85); f.mCurve.set(0.95); f.blush.set(1.25);
            }
            if (H > 2.3) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "cocoa": { // 泡熱可可：捧著杯子等它涼
          const H = this._tapT(t);
          if (H < 0) {
            P.sy -= 0.018; P.rootY += 6; P.headY += 10;
            P.armLShoulder += 26; P.armRShoulder -= 26;
            P.armLElbow += 20; P.armRElbow -= 20;
            f.pupilY.set(0.6); f.eyeOpen.set(0.7); f.mOpen.set(t % 2 < 0.3 ? 0.3 : 0.05); f.mRound.set(0.8);
            // 熱氣原本是用思考點點代打，但它就落在嘴巴上，看起來像他在臉上想事情。
            // 改成手邊一點暖暖的閃光：位置在胸口以下，不會壓到臉。
            this.fxIn -= dt;
            if (this.fxIn <= 0) {
              this.fxIn = 1.1;
              p.fx.spawn("sparkle", { x: 790, y: 700, vy: -46, vx: 6, life: 1.2, s0: 0.2, s1: 0.6 });
            }
            if (t > 6.4) { this._faceReset(); this._end(); }
          } else {                                  // 有人端過來 → 喝一口，整隻暖起來
            if (H < 0.9) {
              P.headY += 14; f.eyeOpen.set(0.3); f.mOpen.set(0.35); f.mRound.set(0.85);
            } else {
              P.sy += 0.02; P.rootY -= 4; P.headY -= 4; P.headRot += Math.sin(H * 1.1) * 2;
              f.eyeOpen.set(0.1); f.eyeArc.set(0.95); f.mOpen.set(0); f.mCurve.set(0.85); f.blush.set(1.4);
              if (this._at(H, dt, 1)) p.fx.spawn("heart", { x: 880, y: 400, life: 1.6, s1: 1.25 });
            }
            if (H > 2.8) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "storybook": { // 看故事書：低頭一行一行讀（「幫他翻頁」互動已移除）
          P.headY += 16; P.headRot += Math.sin(t * 0.5) * 1.6;
          P.armLShoulder += 22; P.armRShoulder -= 22;
          f.pupilY.set(0.72); f.pupilX.set(Math.sin(t * 1.9) * 0.55);   // 眼睛一行一行掃
          f.eyeOpen.set(0.78); f.mCurve.set(0.35); f.mWide.set(0.2);
          if (t > 6.8) { this._faceReset(); this._end(); }
          break;
        }

        case "painting": { // 畫畫：手上下刷，偶爾歪頭端詳
          const H = this._tapT(t);
          if (H < 0) {
            P.armRShoulder -= 34 + Math.sin(t * 5.2) * 12;
            P.armRElbow -= 16 + Math.sin(t * 5.2) * 8;
            P.headRot += Math.sin(t * 0.75) * 4; P.headY += 6;
            f.pupilX.set(0.45); f.pupilY.set(0.3); f.eyeOpen.set(0.85); f.mCurve.set(0.4);
            if (t > 6.6) { this._faceReset(); this._end(); }
          } else {                                  // 被看到畫了什麼 → 害羞地把畫轉過來
            P.headRot += Math.sin(H * 1.4) * 3; P.headY += 4;
            P.armRShoulder -= Math.max(0, 34 - H * 40);
            f.eyeOpen.set(0.2); f.eyeArc.set(0.85); f.pupilX.set(0);
            f.mCurve.set(0.8); f.mWide.set(0.35); f.blush.set(1.5);
            if (this._at(H, dt, 0.6)) p.fx.spawn("heart", { x: 1000, y: 340, life: 1.5, s1: 1.2 });
            if (H > 2.5) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "kite": { // 放風箏：仰頭拉線，身體被風帶著晃
          const H = this._tapT(t);
          if (H < 0) {
            P.headY -= 14; P.headRot += Math.sin(t * 0.8) * 3;
            P.armLShoulder += 50; P.armLElbow += 18 + Math.sin(t * 2.1) * 8;
            P.rootRot += Math.sin(t * 0.9) * 1.8; P.rootX += Math.sin(t * 0.9) * 6;
            P.scarfRot += Math.sin(t * 1.4) * 6;
            f.pupilY.set(-0.8); f.pupilX.set(-0.4 + Math.sin(t * 0.7) * 0.25);
            f.eyeOpen.set(1.05); f.mOpen.set(0.2); f.mRound.set(0.4); f.mCurve.set(0.6);
            if (t > 6.8) { this._faceReset(); this._end(); }
          } else {                                  // 有人幫忙拉 → 風箏衝高，興奮跳起來
            P.rootY -= Math.abs(Math.sin(H * 5)) * 16; P.headY -= 18;
            P.armLShoulder += 62; P.armRShoulder -= 62; P.scarfRot += 10;
            f.pupilY.set(-0.85); f.eyeOpen.set(1.3); f.pupilScale.set(1.1);
            f.mOpen.set(0.55); f.mWide.set(0.8); f.mCurve.set(0.9); f.blush.set(1.2);
            if (this._at(H, dt, 0.2)) p.fx.spawn("sparkle", { x: 560, y: 110, life: 1.5, s1: 1.4 });
            if (H > 2.6) { this._faceReset(); f.pupilScale.set(1); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "snowAngel": { // 雪天使：整隻攤平在雪地上
          const H = this._tapT(t);
          if (H < 0) {
            const u = Math.min(1, t / 0.9);
            P.sy -= 0.075 * u; P.sx += 0.07 * u; P.rootY += 26 * u; P.headY += 18 * u;
            P.armLShoulder += 44 * u; P.armRShoulder -= 44 * u;
            P.legLRot += 9 * u; P.legRRot -= 9 * u;
            f.eyeOpen.set(0.45); f.pupilY.set(-0.5); f.mCurve.set(0.55);
            if (t > 6.2) { this._faceReset(); this._end(); }
          } else {                                  // 被拍拍 → 開心地揮出雪天使的翅膀
            const w = Math.sin(H * 7);
            P.sy -= 0.07; P.sx += 0.065; P.rootY += 24; P.headY += 16;
            P.armLShoulder += 44 + w * 22; P.armRShoulder -= 44 + w * 22;
            P.legLRot += 9 + w * 5; P.legRRot -= 9 + w * 5;
            f.eyeOpen.set(0.12); f.eyeArc.set(1);
            f.mOpen.set(0.4); f.mWide.set(0.8); f.mCurve.set(0.95); f.blush.set(1.2);
            // 原本這裡揚起的是雪花；待機不再下雪，改用亮粉表示雪地被掃起來
            this.fxIn -= dt;
            if (this.fxIn <= 0) {
              this.fxIn = 0.5;
              p.fx.spawn("sparkle", { x: 560 + Math.random() * 460, y: 780, vy: -60, life: 1.1, s1: 0.7 });
            }
            if (H > 2.8) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "penguin": { // 企鵝朋友：發現旁邊有隻企鵝，好奇打量
          const H = this._tapT(t);
          if (H < 0) {
            P.headRot += 3.5 + Math.sin(t * 0.9) * 1.4; P.headX += 8; P.rootX += 3;
            f.pupilX.set(0.8); f.pupilY.set(0.35); f.eyeOpen.set(1.12); f.pupilScale.set(1.06);
            f.mOpen.set(0.14); f.mRound.set(0.6);
            // 「這是什麼？」原本用問號表示，但它壓在臉上；歪頭與瞳孔已經講得很清楚了
            if (t > 6.6) { this._faceReset(); f.pupilScale.set(1); this._end(); }
          } else {                                  // 幫他們介紹 → 一起揮手，變朋友了
            P.armRShoulder -= 46 + Math.sin(H * 7) * 12; P.armRElbow -= 20;
            P.rootX += 5; P.headRot += 2.5 + Math.sin(H * 3) * 1.6;
            f.pupilX.set(0.5); f.eyeOpen.set(0.14); f.eyeArc.set(1); f.pupilScale.set(1);
            f.mOpen.set(0.35); f.mWide.set(0.78); f.mCurve.set(0.95); f.blush.set(1.2);
            if (this._at(H, dt, 0.5)) p.fx.spawn("heart", { x: 1020, y: 420, life: 1.6, s1: 1.25 });
            if (H > 2.6) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "skate": { // 溜冰：左右滑步，重心跟著換
          const H = this._tapT(t);
          if (H < 0) {
            const g = Math.sin(t * 1.55);
            P.rootX += g * 20; P.rootRot += g * 4.5; P.headRot -= g * 2.4;
            P.legLRot += g * 8; P.legRRot += g * 8; P.scarfRot -= g * 7;
            P.armLShoulder += g * 20; P.armRShoulder += g * 20;
            f.pupilX.set(PET.clamp(g * 0.6, -1, 1)); f.eyeOpen.set(1.05); f.mCurve.set(0.7);
            if (t > 6.8) { this._faceReset(); this._end(); }
          } else {                                  // 有人加油 → 轉一圈，張手謝幕
            if (H < 1.1) {
              P.rootRot += Math.sin(H / 1.1 * Math.PI * 2) * 9;
              P.sx -= 0.04; P.sy += 0.045; P.rootY -= 12;
              P.scarfRot += 14; f.eyeOpen.set(1.15);
            } else {
              P.armLShoulder += 46; P.armRShoulder -= 46; P.rootY -= 4; P.headY -= 6;
              f.eyeOpen.set(0.12); f.eyeArc.set(1);
              f.mOpen.set(0.4); f.mWide.set(0.85); f.mCurve.set(0.95); f.blush.set(1.15);
              if (this._at(H, dt, 1.2)) p.fx.spawn("sparkle", { x: 774, y: 300, life: 1.5, s1: 1.5 });
            }
            if (H > 3) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "lantern": { // 放天燈：捧著天燈，眼睛跟著它往上
          const H = this._tapT(t);
          if (H < 0) {
            P.armLShoulder += 40; P.armRShoulder -= 40;
            P.armLElbow += 18; P.armRElbow -= 18;
            P.headY -= 6 + Math.sin(t * 0.7) * 2;
            f.pupilY.set(-0.6); f.eyeOpen.set(1.05); f.pupilScale.set(1.06);
            f.mCurve.set(0.6); f.mWide.set(0.22);
            this.fxIn -= dt;
            if (this.fxIn <= 0) { this.fxIn = 1.8; p.fx.spawn("sparkle", { x: 960, y: 200, vy: -34, life: 1.6, s1: 1.1 }); }
            if (t > 6.6) { this._faceReset(); f.pupilScale.set(1); this._end(); }
          } else {                                  // 一起放上去 → 目送它飛走，感動
            P.armLShoulder += 58; P.armRShoulder -= 58;
            P.headY -= 16 - H * 2; P.sy += 0.02; P.rootY -= 5;
            f.pupilY.set(-0.85); f.eyeOpen.set(0.9); f.pupilScale.set(1);
            f.mOpen.set(0.12); f.mCurve.set(0.8); f.mWide.set(0.35); f.blush.set(1.2);
            if (this._at(H, dt, 0.3)) p.fx.spawn("sparkle", { x: 940, y: 150, vy: -60, life: 2, s1: 1.5 });
            // （原本目送天燈飛走會感動到泛淚。待機一律不出現眼淚，改成多一顆星光。）
            if (this._at(H, dt, 1.4)) p.fx.spawn("sparkle", { x: 1010, y: 120, vy: -50, life: 1.8, s1: 1.2 });
            if (H > 3) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        // ---------- 嘴饞 ----------
        case "drool": { // 流口水嘴饞：盯著看不見的好料，嘴角一滴口水越垂越長
          const H = this._tapT(t);
          if (H < 0) {
            // 身體微微往前傾、跟著想像中的食物左右挪；動作刻意做大一點，
            // 因為口水的晃動是被嘴角的移動速度驅動的——頭不動就看不出黏稠感。
            const sway = Math.sin(t * 0.9) + Math.sin(t * 2.3) * 0.32;
            P.rootRot += sway * 2.1; P.headX += sway * 13; P.headY += 4 + Math.sin(t * 1.7) * 3.5;
            P.headRot += sway * 3;
            P.armLShoulder += 10; P.armRShoulder -= 10;
            f.pupilX.set(PET.clamp(sway * 0.5, -1, 1)); f.pupilY.set(0.55);
            f.eyeOpen.set(1.15); f.pupilScale.set(1.12);
            const mo = 0.3 + Math.sin(t * 1.7) * 0.1;
            f.mOpen.set(mo); f.mRound.set(0.5);
            f.mWide.set(0.45); f.mCurve.set(0.35); f.blush.set(1.1);
            // 吞口水：每 3.2 秒縮一下嘴，口水也跟著歸零重新積
            const cycle = t % 3.2;
            const swallow = cycle > 2.9;
            if (swallow) { f.mOpen.set(0.05); f.mRound.set(0.3); }
            this._drool(p, swallow ? 0 : PET.clamp(cycle / 2.4, 0, 1), P, dt, swallow ? 0 : mo);
            if (t > 9.6) { this._faceReset(); f.pupilScale.set(1); f.blush.set(0.75); this._end(); }
          } else {                                  // 餵他一口 → 大口吃掉，滿足到瞇眼
            this._drool(p, 0);                      // 口水先收掉，不然邊吃邊流很怪
            if (H < 0.5) {                          // 張大嘴湊上去
              const u = PET.smooth(H / 0.5);
              P.headY += 12 * u; P.headRot -= 2 * u;
              f.mOpen.set(0.95); f.mRound.set(0.95); f.eyeOpen.set(0.45);
            } else if (H < 1.6) {                   // 嚼嚼嚼
              const chew = Math.sin((H - 0.5) * 16);
              P.headY += 8 + chew * 4; P.headRot += chew * 1.6;
              P.sy += 0.012 * chew;
              f.mOpen.set(0.22 + chew * 0.16); f.mRound.set(0.7); f.mWide.set(0.4);
              f.eyeOpen.set(0.2); f.eyeArc.set(0.7); f.blush.set(1.3);
            } else {                                // 滿足：身體鬆下來、瞇眼傻笑
              P.sy += 0.02; P.rootY -= 3; P.headY += 2;
              P.headRot += Math.sin(H * 1.4) * 2.4;
              f.eyeOpen.set(0.1); f.eyeArc.set(1);
              f.mOpen.set(0); f.mCurve.set(0.95); f.mWide.set(0.55); f.blush.set(1.4);
              if (this._at(H, dt, 1.75)) p.fx.spawn("heart", { x: 1080, y: 120, vy: -46, life: 1.6, s1: 1.1 });
            }
            if (H > 3.1) { this._faceReset(); f.pupilScale.set(1); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        // ---------- 會飛的小生物 ----------
        // 三種都共用 _critter()：由這裡算路徑，眼睛用 _watch() 跟著看。
        case "bee": { // 蜜蜂嗡嗡：繞著鼻子打轉，金孫緊張又不敢動
          const H = this._tapT(t);
          const c = this._critter(p, "bee");
          if (H < 0) {
            // 8 字形繞著頭飛，一開始掃過大半個畫面，之後才慢慢收到鼻子前面。
            // 橫向 ±430 只到熊的兩側；舞台是 x 320..1228，所以放大到 ±700 才會
            // 真的飛滿整個畫面（含熊的外側空間）。
            const a = t * 1.35;
            const close = PET.clamp((t - 1.2) / 5.4, 0, 1);
            const cx = 774 + Math.sin(a) * PET.lerp(700, 165, close);
            const cy = 330 + Math.sin(a * 2) * PET.lerp(420, 80, close)
              + Math.sin(t * 0.7) * PET.lerp(120, 20, close);
            c.at(cx, cy, Math.cos(a) * 26, 3.2, t, 1);
            this._watch(f, cx, cy);
            // 蜜蜂靠近時身體僵住、微微發抖，不敢揮手
            P.sy -= 0.014 * close;
            P.rootRot += Math.sin(t * 22) * 0.9 * close;
            P.headX += PET.clamp((cx - 774) * 0.016, -16, 16);
            P.headRot += PET.clamp((cx - 774) * 0.006, -6, 6);
            P.headY += PET.clamp((cy - 330) * 0.012, -14, 16);
            f.eyeOpen.set(PET.lerp(1.1, 1.3, close)); f.pupilScale.set(1 + close * 0.12);
            f.browShow.set(close * 0.6); f.browTilt.set(-0.25);
            f.mOpen.set(0.06); f.mRound.set(0.55); f.mWide.set(0.16);
            if (t > 9.2) { this._faceReset(); f.pupilScale.set(1); this._end(); }
          } else {                                  // 給牠一朵花 → 蜜蜂飛走採蜜，金孫鬆一口氣
            const u = Math.min(1, H / 1.8);
            const cx = PET.lerp(700, 380, PET.smooth(u));
            const cy = PET.lerp(320, 90, PET.smooth(u)) + Math.sin(H * 3) * 18;
            c.at(cx, cy, -18, 3.2 - u * 1.1, t, 1 - PET.smooth(Math.max(0, (u - 0.7) / 0.3)));
            this._watch(f, cx, cy);
            P.sy += 0.02 * u; P.headY -= 4 * u;
            P.armRShoulder -= 34 * PET.smooth(Math.min(1, H / 0.6));   // 舉花的那隻手
            f.eyeOpen.set(PET.lerp(1.25, 0.2, u)); f.eyeArc.set(u * 0.9);
            f.mOpen.set(0.1); f.mCurve.set(0.4 + u * 0.5); f.mWide.set(0.3); f.blush.set(1.2);
            if (H > 2.6) { this._faceReset(); f.blush.set(0.75); this._end(); }
          }
          break;
        }

        case "dragonfly": { // 蜻蜓來了：停在半空中，金孫慢慢伸手想讓牠停下來
          const H = this._tapT(t);
          const c = this._critter(p, "dfly");
          if (H < 0) {
            // 蜻蜓的飛法是「衝一段、急停、再衝」，所以位置用階梯狀的目標點。
            // 落點範圍拉到幾乎整個舞台（x 380..1170、y -30..760），衝刺也更快，
            // 這樣它才像在整個畫面裡巡邏，而不是在熊的頭上繞小圈。
            const SPAN_X = 790, X0 = 380, SPAN_Y = 790, Y0 = -30;
            // 落點要用真的雜湊打散。踩過兩個坑：
            //   `(n*9301+49297) % 233280` 是把 LCG 的遞迴式直接餵 n，對相鄰的 n
            //     幾乎是線性的——實測連續三段只走了 120 單位，蜻蜓等於在原地抖。
            //   `fract(sin(n*127.1)*43758)` 也不行：127.1 rad 對 2π 取餘只有 1.44，
            //     相鄰 n 的相位只前進一點點，跟奇偶項一相乘就整排偏在同一側。
            // 用整數雜湊（Math.imul + xorshift）才會真的均勻。
            const rnd = (n, k) => {
              let h = Math.imul(n + k * 7919, 374761393) ^ 0;
              h = Math.imul(h ^ (h >>> 13), 1274126177) ^ 0;
              return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
            };
            // 每一段強制換到畫面的另一半：蜻蜓才會「橫越」而不是在同一區打轉
            const at = (n) => [
              X0 + ((n & 1) * 0.5 + rnd(n, 1) * 0.5) * SPAN_X,
              Y0 + ((n & 2 ? 0.5 : 0) + rnd(n, 2) * 0.5) * SPAN_Y,
            ];
            const leg = Math.floor(t / 1.25);
            const u = PET.smooth(PET.clamp((t % 1.25) / 0.42, 0, 1));
            const [px, py] = at(leg), [qx, qy] = at(leg + 1);
            const cx = PET.lerp(px, qx, u), cy = PET.lerp(py, qy, u);
            c.at(cx, cy, PET.clamp((qx - px) * 0.03, -26, 26), 3.4, t, 1);
            this._watch(f, cx, cy);
            P.headX += PET.clamp((cx - 774) * 0.02, -16, 16);
            P.headRot += PET.clamp((cx - 774) * 0.006, -6, 6);
            P.headY += PET.clamp((cy - 330) * 0.014, -16, 18);
            f.eyeOpen.set(1.16); f.pupilScale.set(1.08);
            f.mOpen.set(0.12); f.mRound.set(0.6); f.mWide.set(0.2);
            if (t > 9.4) { this._faceReset(); f.pupilScale.set(1); this._end(); }
          } else {                                  // 伸出手指 → 蜻蜓真的停上來，屏住呼吸
            const u = PET.smooth(Math.min(1, H / 1.1));
            const cx = PET.lerp(620, 1002, u), cy = PET.lerp(150, 620, u);   // 停到右手指尖
            c.at(cx, cy, PET.lerp(-20, 0, u), 3.4, t, 1);
            this._watch(f, cx, cy);
            P.armRShoulder -= 52 * u; P.armRElbow -= 18 * u; P.handRFlex += 0.1 * u;
            P.sy -= 0.012 * u;                       // 屏住呼吸：整個人縮住不敢動
            P.rootRot += Math.sin(H * 1.1) * 0.7;
            f.eyeOpen.set(PET.lerp(1.16, 1.3, u)); f.pupilScale.set(1.12);
            f.mOpen.set(0); f.mCurve.set(0.55); f.mWide.set(0.2); f.blush.set(1.15 + u * 0.15);
            if (this._at(H, dt, 1.3)) p.fx.spawn("sparkle", { x: 1060, y: 560, life: 1.1, s1: 0.9 });
            if (H > 3.2) { this._faceReset(); f.pupilScale.set(1); f.blush.set(0.75); this._end(); }
          }
          break;
        }
      }
    }

    // 口水。amount 0..1 是「積了多少」，其餘全部由物理決定，不是把固定形狀拉長：
    //   · 長度用一個「重到很難拉回去」的彈簧追目標值 → 流下來慢、縮回去更慢（黏稠）
    //   · 側向偏移被嘴角的移動速度反向踢一下再慢慢回正 → 頭一甩它會落後、然後晃回來
    //   · 中段的甩出量是側偏的一半再多落後一點，所以整條是「S 形跟上來」而不是硬平移
    //   · 珠子越積越大；超過臨界長度就斷掉，變成一顆會落下的水滴（fx 的 drip）
    // fx 層掛在 svg 根部、不跟著頭走，所以嘴角座標要自己補上頭的位移與旋轉，
    // 否則頭一歪口水就會留在原地，看起來像浮在臉旁邊。
    _drool(p, amount, P, dt, mouthOpen) {
      const d = this.drl || (this.drl = { len: 6, v: 0, sway: 0, swayV: 0, px: null, py: null });
      if (amount <= 0.02) {
        if (this.droolEl) { this.droolEl.remove(); this.droolEl = null; }
        d.len = 5; d.v = 0; d.sway = 0; d.swayV = 0; d.px = null; d.py = null;
        return;
      }
      // 起點就是**現在這一幀的右嘴角**（face.js 畫完嘴之後記下來的），
      // 不是一個猜出來的固定點——嘴一張大、笑開，嘴角會移動好幾十單位，
      // 用固定座標就會變成「從臉頰上憑空冒出一條」。
      const mc = p.face && p.face.mouthCorner ? p.face.mouthCorner() : { x: 817, y: 479 };
      const MX = mc.x - 3, MY = mc.y + 4;    // 往嘴唇內縮一點，看起來是從嘴縫滲出來
      const HX = 774, HY = 545;              // 頭的樞紐＝脖子（同 pet.js HEAD_OX/OY）
      const rot = (P && P.headRot) || 0;
      const a = (rot * Math.PI) / 180;
      const ox = MX - HX, oy = MY - HY;
      // 嘴張得越開，嘴角越往下、口水的著點也跟著走
      // 嘴角已經含了張嘴的位移（mouthCorner 是實際畫出來的位置），
      // 這裡只要再套上頭的旋轉與平移就好
      const x = HX + ox * Math.cos(a) - oy * Math.sin(a) + ((P && P.headX) || 0);
      const y = HY + ox * Math.sin(a) + oy * Math.cos(a) + ((P && P.headY) || 0);

      const h = PET.clamp(dt || 0.016, 0.001, 0.05);
      // --- 長度：黏稠 = 高慣性、低回彈 ---
      const target = 8 + amount * 46 + (mouthOpen || 0) * 10;
      d.v += (target - d.len) * 26 * h;      // 往目標拉
      d.v += 34 * h;                          // 重力：只往下，所以縮回去比流下來慢
      d.v *= Math.exp(-6.5 * h);              // 黏滯阻尼
      d.len = PET.clamp(d.len + d.v * h, 3, 92);

      // --- 側偏：被嘴角的移動速度反向踢，然後慢慢回正 ---
      if (d.px != null) {
        const vx = (x - d.px) / h, vy = (y - d.py) / h;
        d.swayV -= vx * 0.055;                // 頭往右移 → 口水落在左邊
        d.v -= vy * 0.02;                     // 頭往下沉 → 這一條會先被壓短一點
      }
      d.px = x; d.py = y;
      d.swayV += -d.sway * 62 * h;            // 回正
      d.swayV *= Math.exp(-4.2 * h);
      d.sway = PET.clamp(d.sway + d.swayV * h, -18, 18);

      const r = 1.7 + Math.min(1, d.len / 46) * 3.6;   // 末端珠子越積越大

      // --- 斷裂：太長就掉下去 ---
      if (d.len > 58) {
        p.fx.spawn("drip", {
          x: x + d.sway * 0.9, y: y + d.len,
          vx: d.swayV * 0.35, vy: 40, gravity: 900,
          life: 0.8, s0: r / 9, s1: r / 8.2, sway: 0, swayHz: 0,
        });
        d.len = 9; d.v = 0; d.swayV *= 0.3;
      }

      if (!this.droolEl) this.droolEl = p.fx.droolStrand();
      this.droolEl.update({
        x, y, rot, scale: 2.2,
        len: d.len, sway: d.sway,
        bulge: d.sway * 0.62,                  // 中段落後一點 → S 形
        r,
        alpha: Math.min(1, amount * 4),
      });
    }

    // 借一隻小生物出來；同一次待機內重複呼叫拿到的是同一隻
    _critter(p, type) {
      if (!this.critterEl || this.critterType !== type) {
        if (this.critterEl) this.critterEl.remove();
        this.critterEl = p.fx.critter(type);
        this.critterType = type;
      }
      return this.critterEl;
    }

    // 眼睛追著畫面上某個點看（座標是熊的 viewBox 座標）
    _watch(f, x, y) {
      f.pupilX.set(PET.clamp((x - 774) / 340, -1, 1));
      f.pupilY.set(PET.clamp((y - 330) / 360, -1, 1));
    }

    // 可互動待機用：還沒被按回 -1，按了之後回「按下去到現在」的秒數
    _tapT(t) {
      const c = this.cur;
      return c && c.hit ? t - c.hitT : -1;
    }

    _enter(key) {
      // 需要隨機參數的行為在這裡先決定；step 內也有惰性後備，兩邊都安全
      if (key === "groom" && this.cur) this.cur.side = Math.random() < 0.5 ? -1 : 1;
      const o = PET.IDLE_LIST[key];
      if (o && o.tap && this.cur) {
        this.cur.tap = o.tap; this.cur.hit = false; this.cur.hitT = 0;
        this.pet._emit("idleTap", { key, state: "show", tap: o.tap, zh: o.zh });
      }
    }
  };
})();
