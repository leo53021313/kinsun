// pet.js — Pet 主體：組裝 SVG、姿勢/臉部彈簧、rAF 主迴圈、對外 API
(function () {
  const PET = (window.PET = window.PET || {});
  const NS = "http://www.w3.org/2000/svg";

  const ROOT_OX = 774, ROOT_OY = 1064;   // 縮放/旋轉原點：腳底中心
  const HEAD_OX = 774, HEAD_OY = 545;    // 頭部樞紐：脖子

  // 頭部擺動上限：超過這個角度動態頸層就會從圍巾旁邊露出來，看起來像脖子被拉長。
  // 用 tanh 做軟飽和而非硬切，小角度手感不變、大角度平滑收斂到上限。
  const HEAD_ROT_MAX = 5.5;   // 度
  const HEAD_X_MAX = 15;      // SVG 單位
  // 抬頭上限：頭往上超過這個距離，下巴的溶接帶就會離開身體層頂端（y=514），
  // 中間會露出背景。抬 26 以內永遠有身體的同一塊毛在後面接著。
  const HEAD_Y_UP_MAX = 22;
  const softLimit = (v, max) => max * Math.tanh(v / max);

  // 布料剪力支點：下襬。位移在這裡是 0、往上線性放大到領口最大，
  // 所以圍巾會跟著頭「延伸」出去，而腳邊與腿層之間不會產生接縫。
  const CLOTH_PIVOT = 1010;

  // 五種聆聽姿勢：進入聆聽時抽一種，臉在這裡定調、身體在 _tick 的 listening 段。
  PET.LISTEN_STYLES = [
    { key: "nodAlong", zh: "點頭附和",
      face: { eyeOpen: 1.06, mCurve: 0.55, mWide: 0.28, pupilY: 0.32 } },
    { key: "earIn", zh: "側耳貼近",
      face: { eyeOpen: 0.92, eyeArc: 0.2, mCurve: 0.42, mWide: 0.22, pupilX: -0.55, pupilY: 0.1 } },
    { key: "leanCurious", zh: "好奇探身",
      face: { eyeOpen: 1.22, pupilScale: 1.1, mOpen: 0.12, mRound: 0.55, mCurve: 0.5, pupilY: 0.28 } },
    { key: "takingNotes", zh: "邊聽邊記",
      face: { eyeOpen: 0.88, browShow: 0.42, browTilt: 0.05, mCurve: 0.3, mWide: 0.2, pupilX: -0.35, pupilY: -0.42 } },
    { key: "quietGaze", zh: "安靜凝視",
      face: { eyeOpen: 0.98, mCurve: 0.72, mWide: 0.34, blush: 0.95, pupilY: 0.18 } },
  ];

  PET.Pet = class {
    constructor(mount) {
      // --- DOM 組裝 ---
      mount.innerHTML = window.BEAR_SVG;
      const svg = (this.svg = mount.querySelector("svg"));
      svg.setAttribute("viewBox", "320 -90 908 1250");
      svg.setAttribute("preserveAspectRatio", "xMidYMax meet");
      svg.style.width = "100%"; svg.style.height = "100%";
      this.artistic = svg.getAttribute("data-renderer") === "artistic-raster";

      const headSrc = svg.querySelector("#head");
      const bodySrc = svg.querySelector("#body");
      const rootG = (this.rootG = document.createElementNS(NS, "g"));
      const headG = (this.headG = document.createElementNS(NS, "g"));
      const neckG = (this.neckG = document.createElementNS(NS, "g"));
      const bodyG = (this.bodyG = document.createElementNS(NS, "g"));

      // 動態頸層：頭部傾斜時，用藏在頭與圍巾後方的毛色補片銜接斷口。
      // 素材可用 data-neck 覆寫錨點；目前熊圖使用下列預設位置。
      const defaultNeck = "575,515,950,520,580,595,950,590";
      this.headScale = 1.035;
      this.headDrop = 3;
      // 藝術版的頭部下緣已經改成在下巴白毛上溶接（見 tools/21_build_artistic_svg.py），
      // 身體層本來就含同一塊毛，不需要再補一片幾何頸層——留著只會多一道淡淡的邊。
      // 舊的向量素材沒有這層溶接，仍然要靠補片，所以介面保留。
      this.neckOn = !this.artistic;
      const na = (svg.getAttribute("data-neck") || defaultNeck)
        .split(",").map(Number);
      this.neckA = { hL: { x: na[0], y: na[1] }, hR: { x: na[2], y: na[3] },
                     bL: { x: na[4], y: na[5] }, bR: { x: na[6], y: na[7] } };
      // 新頸線沿補片外側走，頭部左右傾斜時仍能看見完整、自然的黑色輪廓。
      this.neckLineA = { hL: { x: 590, y: 520 }, hR: { x: 940, y: 522 },
                         bL: { x: 590, y: 590 }, bR: { x: 940, y: 586 } };
      this.neckFill = document.createElementNS(NS, "path");
      this.neckFill.setAttribute("fill", this.artistic ? "#f5f3f2" : "#F8FBFC");
      // 藝術點陣圖本身已包含完整針織圍巾；只留極淡的頸部保險層，避免形成另一種畫風。
      this.neckFill.setAttribute("opacity", this.artistic ? "0.08" : "1");
      this.neckSideL = document.createElementNS(NS, "path");
      this.neckSideR = document.createElementNS(NS, "path");
      for (const s of [this.neckSideL, this.neckSideR]) {
        s.setAttribute("fill", "none");
        s.setAttribute("stroke", this.artistic ? "#777275" : "#0d0d0d");
        s.setAttribute("stroke-width", this.artistic ? "7" : "14");
        s.setAttribute("opacity", this.artistic ? "0.06" : "1");
        s.setAttribute("stroke-linecap", "round");
      }
      neckG.appendChild(this.neckFill);
      neckG.appendChild(this.neckSideL);
      neckG.appendChild(this.neckSideR);

      // 圍巾材質只由 bodyArt 提供；不再疊加另一套幾何向量，避免硬邊與畫風斷層。
      // 地面陰影
      this.shadow = document.createElementNS(NS, "ellipse");
      this.shadow.setAttribute("cx", ROOT_OX); this.shadow.setAttribute("cy", 1082);
      this.shadow.setAttribute("rx", 195); this.shadow.setAttribute("ry", 26);
      this.shadow.setAttribute("fill", "rgba(20,40,60,0.12)");
      svg.insertBefore(this.shadow, headSrc);
      svg.insertBefore(rootG, headSrc);
      // 頭與身體沿用相同的 head/body 契約；目前預設是高保真透明點陣層，
      // 舊版向量素材仍可由 tools/20_revector.py 重新產出作為回復基線。
      // （舊版有 hatPomFill / faceSeamFill / oldNeckMask / chinLine 四塊寫死的白色與
      //   黑線補片，用來補素材去背後缺掉的白毛與下巴輪廓；那些形狀會溢出輪廓外蓋到
      //   背景。現在描線階段就把缺口補好、白毛完整保留，補片全部拿掉。）
      headG.appendChild(headSrc);
      this.body = new PET.Body(bodyG, bodySrc);
      // 紙娃娃層序：頸(保險,最底) -> 身 -> 頭(最上,自然壓在圍巾上)
      rootG.appendChild(neckG); rootG.appendChild(bodyG); rootG.appendChild(headG);
      const fxG = document.createElementNS(NS, "g");
      svg.appendChild(fxG);

      // 臉掛在 headG 最上層（而非 headSrc 內），才不會被舊頸線遮罩與下巴補片蓋住
      this.face = new PET.Face(headG);
      this.fx = new PET.Fx(fxG);
      this.stateMachine = new PET.AnimationStateMachine(this);
      this.behaviorController = new PET.BehaviorController(this);
      this.quality = new PET.AnimationQuality(this);
      this.motionEnabled = true;
      this.motionQuality = "high";

      // --- 狀態 ---
      this.pose = {
        rootX: 0, rootY: 0, rootRot: 0, sx: 0, sy: 0,
        headRot: 0, headX: 0, headY: 0, chestRot: 0,
        armLShoulder: 0, armLElbow: 0, armRShoulder: 0, armRElbow: 0,
        handLFlex: 0, handRFlex: 0, legLRot: 0, legRRot: 0,
        footL: 0, footR: 0, scarfRot: 0,
      };
      this.springs = {};
      for (const k of Object.keys(this.pose)) {
        const arm = k.startsWith("arm");
        this.springs[k] = new PET.Spring(0, arm ? 92 : 70, arm ? 10.5 : 13);
      }

      // 布料彈簧：故意做得又軟又欠阻尼（d < 2√k），頭停下來之後圍巾還會再晃兩下，
      // 這個「跟不上、然後追過頭」才是布料的感覺；剛性彈簧只會變成整片一起平移。
      this.clothLean = new PET.Spring(0, 30, 7.4);
      this.clothStretch = new PET.Spring(0, 38, 9.5);

      this.faceS = {};
      const df = PET.defaultFace();
      for (const k of Object.keys(df)) this.faceS[k] = new PET.Spring(df[k], 150, 21);

      this.emotion = null; this.emotionKey = "calm"; this.intensity = 2;
      this.clip = null; this.clipT = 0; this.firedFx = new Set();
      this.linger = {};
      this.thinking = false; this._thinkT = 0;
      this.listening = false;
      this.listenStyle = 1;
      this._listenT = 0;
      // 天氣環境姿勢：不管在做什麼情緒/待機都持續疊加（頂風前傾、發抖、縮著、熱到垂下去）
      this.weatherPose = null;
      this.talking = false;
      this.talkBob = new PET.Spring(0, 220, 16);
      this.blinkIn = 2.2 + Math.random() * 2.5;
      this.blinkPhase = -1;
      this.lookTarget = null;   // {x,y} -1..1 暫時視線
      this._fxLoopT = 0;
      this.t = 0;
      this.idle = null;          // 由 idle.js 掛上

      this._last = performance.now();
      const loop = (now) => {
        const dt = Math.min((now - this._last) / 1000, 0.06);
        this._last = now;
        this._tick(dt);
        requestAnimationFrame(loop);
      };
      requestAnimationFrame(loop);
    }

    // ================= 對外 API =================
    setEmotion(key, opts = {}) {
      const E = PET.EMOTIONS[key];
      if (!E) return;
      const soft = !!opts.soft;
      const inten = PET.clamp(opts.intensity || 2, 1, 3);
      this.emotionKey = key; this.intensity = inten;
      const blend = soft ? 0.45 : [0.62, 0.82, 1][inten - 1];
      const df = PET.defaultFace();
      for (const k of Object.keys(df)) {
        const tv = PET.lerp(df[k], E.face[k], blend);
        this.faceS[k].set(tv);
      }
      if (!soft) {
        this.listening = false; this.thinking = false;
        this.emotion = E;
        this.clip = E.clip; this.clipT = 0; this.firedFx = new Set();
        this.linger = E.linger || {};
        this._fxLoopT = 0;
        if (this.idle) this.idle.suspend();
        if (this.stateMachine) this.stateMachine.set("emotion", { intent: this.behavior });
      }
      this._emit("emotion", { key, intensity: inten, soft });
    }

    backToIdle() {
      this.emotion = null; this.clip = null; this.linger = {};
      this.listening = false; this.thinking = false;
      this.setEmotion("calm", { soft: true });
      this.emotionKey = "calm";
      if (this.stateMachine) this.stateMachine.set("idle");
      if (this.idle) this.idle.resume();
    }

    // 結構化語意先驅動身體，再由完成回呼提交臉部情緒。
    setMotionIntent(intent) {
      this.behavior = PET.normalizeBehavior ? PET.normalizeBehavior(intent) : intent;
      if (this.stateMachine) this.stateMachine.setIntent(this.behavior);
      this._emit("behavior", this.behavior);
      return this.behavior;
    }

    beginBehavior(intent) {
      const b = this.behaviorController ? this.behaviorController.begin(intent) : this.setMotionIntent(intent);
      if (this.stateMachine) this.stateMachine.set("speaking", { intent: b });
      return b;
    }

    applyBehavior(intent) {
      const b = this.behaviorController ? this.behaviorController.begin(intent) : this.setMotionIntent(intent);
      if (this.behaviorController) this.behaviorController.finish();
      if (this.stateMachine) this.stateMachine.set(b.hand_gesture !== "none" ? "action" : "emotion", { intent: b });
      return b;
    }

    playAction(action, opts = {}) {
      const b = PET.normalizeBehavior({
        primary_emotion: opts.emotion || this.emotionKey || "calm",
        hand_gesture: action, body_posture: opts.posture || "open",
        motion_amplitude: opts.amplitude || 0.7, motion_speed: opts.speed || 0.8,
        duration: opts.duration || 4,
      });
      this.setMotionIntent(b);
      if (this.stateMachine) this.stateMachine.set("action", { intent: b });
      return b;
    }

    // 聆聽：按住麥克風／正在打字時的姿勢。每次進入聆聽隨機抽一種，
    // 按住期間不會中途換型（換型會像動作卡住重播）。放開之後由 main.js 接思考動畫。
    //
    // 這五種都是「沒有情緒」的中性姿勢：金孫還不知道你要說什麼，本來就不該有反應。
    // 差別在專注的方式——點頭附和／側耳貼近／好奇探身／邊聽邊記／安靜凝視。
    listen(on) {
      on = !!on;
      if (this.listening === on) return;
      this.listening = on;
      if (on) {
        this.listenStyle = 1 + ((Math.random() * PET.LISTEN_STYLES.length) | 0);
        this._listenT = 0;
        this.thinking = false;
        this.emotion = null; this.clip = null; this.linger = {};
        const df = PET.defaultFace();
        for (const k of Object.keys(df)) this.faceS[k].set(df[k]);
        const F = PET.LISTEN_STYLES[this.listenStyle - 1].face;
        for (const k in F) this.faceS[k].set(F[k]);
        this.emotionKey = "calm";
        if (this.stateMachine) this.stateMachine.set("listening");
        if (this.idle) this.idle.suspend();
        this._emit("listen", {
          on: true, style: this.listenStyle,
          zh: PET.LISTEN_STYLES[this.listenStyle - 1].zh,
        });
      } else {
        this.faceS.pupilY.set(0); this.faceS.pupilX.set(0);
        this.faceS.pupilScale.set(1); this.faceS.browShow.set(0);
        if (!this.thinking && !this.talking && this.stateMachine) this.stateMachine.set("idle");
        this._emit("listen", { on: false });
      }
    }

    think(on) {
      this.thinking = on; this._thinkT = 0;
      if (on) {
        this.listening = false;
        // 思考時只做思考的動作，不帶任何情緒（情緒要等回話內容決定）
        this.emotion = null; this.clip = null; this.linger = {};
        this.faceS.pupilX.set(-0.55); this.faceS.pupilY.set(-0.6);
        this.faceS.eyeOpen.set(0.72); this.faceS.eyeArc.set(0);
        this.faceS.browShow.set(0.45); this.faceS.browTilt.set(0.1);
        this.faceS.mOpen.set(0); this.faceS.mCurve.set(0.1); this.faceS.mWide.set(0.15);
        this.faceS.blush.set(0.75); this.faceS.tear.set(0); this.faceS.sweat.set(0);
        if (this.stateMachine) this.stateMachine.set("thinking");
        if (this.idle) this.idle.suspend();
      } else {
        this.faceS.pupilX.set(0); this.faceS.pupilY.set(0);
        this.faceS.browShow.set(0);
        if (!this.talking && this.stateMachine) this.stateMachine.set("transition");
      }
    }

    // 視線：x,y ∈ -1..1（null 回正）
    lookAt(x, y) {
      this.lookTarget = x == null ? null : { x, y };
      if (this.lookTarget) {
        this.faceS.pupilX.set(this.lookTarget.x);
        this.faceS.pupilY.set(this.lookTarget.y);
      }
    }

    userActivity() { if (this.idle) this.idle.poke(); }

    // 說話中：由 TalkDriver 每字呼叫
    talkChar(vis) {
      const M = {
        A: { mOpen: 0.9, mWide: 0.55, mRound: 0.15 },
        O: { mOpen: 0.62, mWide: 0.3, mRound: 0.8 },
        E: { mOpen: 0.42, mWide: 0.6, mRound: 0.15 },
        I: { mOpen: 0.3, mWide: 0.95, mRound: 0 },
        U: { mOpen: 0.4, mWide: 0.12, mRound: 1 },
        M: { mOpen: 0.03, mWide: 0.3, mRound: 0.2 },
      }[vis];
      if (!M) { // 標點停頓 → 閉嘴
        this.faceS.mOpen.set(0.05);
        return;
      }
      for (const k in M) { this.faceS[k].vel = 0; this.faceS[k].set(M[k]); }
      this.talkBob.vel -= 150;  // 頭部小顫
    }
    talkStart() { this.talking = true; if (this.stateMachine) this.stateMachine.set("speaking", { intent: this.behavior }); }
    talkEnd() {
      this.talking = false;
      // 嘴回到目前情緒
      const E = PET.EMOTIONS[this.emotionKey] || PET.EMOTIONS.calm;
      const blend = [0.62, 0.82, 1][this.intensity - 1] || 0.82;
      const df = PET.defaultFace();
      for (const k of ["mOpen", "mWide", "mCurve", "mRound"])
        this.faceS[k].set(PET.lerp(df[k], E.face[k], blend));
      if (this.stateMachine) this.stateMachine.set(this.behavior?.hand_gesture !== "none" ? "action" : "emotion", { intent: this.behavior });
    }

    on(ev, fn) { (this._h = this._h || {})[ev] = (this._h[ev] || []).concat(fn); }
    _emit(ev, d) { ((this._h || {})[ev] || []).forEach((f) => f(d)); }

    // ================= 主迴圈 =================
    _tick(dt) {
      this.t += dt;
      const P = {
        rootX: 0, rootY: 0, rootRot: 0, sx: 0, sy: 0,
        headRot: 0, headX: 0, headY: 0, chestRot: 0,
        armLShoulder: 0, armLElbow: 0, armRShoulder: 0, armRElbow: 0,
        handLFlex: 0, handRFlex: 0, legLRot: 0, legRRot: 0,
        footL: 0, footR: 0, scarfRot: 0,
      };

      // 呼吸基線
      const br = Math.sin((this.t * Math.PI * 2) / 3.4);
      P.sy += 0.011 * br; P.headY += 2.5 * br;
      P.armLShoulder += br * 0.75; P.armRShoulder -= br * 0.75;
      P.scarfRot += Math.sin(this.t * 1.45) * 1.4;

      // Blend Tree / procedural full-body layer：在既有情緒剪輯上提供肩、手、腿、重心。
      if (this.motionEnabled && this.stateMachine) this.stateMachine.sample(dt, P);

      // 情緒剪輯
      if (this.clip) {
        this.clipT += dt;
        this.clip.sample(this.clipT, P);
        for (const f of this.clip.fx) {
          if (this.clipT >= f.t && !this.firedFx.has(f)) {
            this.firedFx.add(f);
            this.fx.spawn(f.type, f);
          }
        }
        if (this.clip.tremble) {
          P.rootX += Math.sin(this.t * 78) * this.clip.tremble;
        }
        if (this.clip.done(this.clipT)) this.clip = null;
      }

      // 情緒餘韻 linger
      const L = this.linger;
      if (L.rootRotSwayAmp) P.rootRot += Math.sin(this.t * Math.PI * 2 * (L.rootRotSwayHz || 0.5)) * L.rootRotSwayAmp;
      if (L.rootYBounceAmp) P.rootY -= Math.abs(Math.sin(this.t * Math.PI * L.rootYBounceHz)) * L.rootYBounceAmp;
      if (L.trembleAmp) P.rootX += Math.sin(this.t * (L.trembleHz || 12) * 2) * L.trembleAmp;
      if (L.headRotBase) P.headRot += L.headRotBase;
      if (L.headYBase) P.headY += L.headYBase;

      // 情緒 fx 循環（想睡 Zzz）
      const E = this.emotion;
      if (E && E.fxLoop) {
        this._fxLoopT += dt;
        if (this._fxLoopT >= E.fxLoop.every) { this._fxLoopT = 0; this.fx.spawn(E.fxLoop.type, E.fxLoop); }
      }

      // 聆聽中：五種專注姿勢，每次按住麥克風隨機抽一種，放開前不會換型。
      // 全部只用身體語言，不帶情緒——臉的部分在 listen() 裡就定好了。
      if (this.listening) {
        this._listenT += dt;
        const lt = this._listenT;
        const enter = PET.smooth(PET.clamp(lt / 0.55, 0, 1));   // 進場緩入，不會硬跳
        switch (this.listenStyle) {
          case 1: {  // 點頭附和：每 1.6 秒一次「嗯嗯」，肩膀跟著沉一下
            const nod = Math.max(0, Math.sin(lt * 3.9)) * Math.max(0, Math.sin(lt * 0.62));
            P.headRot += (2.2 + Math.sin(lt * 0.9) * 0.7) * enter;
            P.headY += (5 + nod * 9) * enter;
            P.chestRot += nod * 1.2 * enter;
            P.rootY += 2 * enter; P.sy += 0.006 * enter;
            P.armLShoulder += (9 - nod * 4) * enter; P.armRShoulder -= (9 - nod * 4) * enter;
            P.scarfRot += nod * 3 * enter;
            break;
          }
          case 2: {  // 側耳貼近：把左耳轉向你，一隻手攏在耳邊
            P.headRot -= (5.6 + Math.sin(lt * 0.75) * 0.6) * enter;
            P.headX -= (7 + Math.sin(lt * 0.55) * 2) * enter;
            P.headY += (2 + Math.sin(lt * 1.25) * 1.6) * enter;
            P.armLShoulder += (48 + Math.sin(lt * 1.8) * 4) * enter;
            P.armLElbow += (28 + Math.sin(lt * 1.8) * 3) * enter;
            P.handLFlex += 0.05 * enter;
            P.rootRot -= 1.2 * enter;
            P.scarfRot += Math.sin(lt * 1.15) * 2.6 * enter;
            break;
          }
          case 3: {  // 好奇探身：整隻往前一步，重心壓在前腳
            P.rootRot += (2.4 + Math.sin(lt * 0.8) * 0.6) * enter;
            P.rootX += (6 + Math.sin(lt * 0.7) * 2) * enter;
            P.rootY += 4 * enter; P.sy += 0.012 * enter;
            P.headRot += (-2.4 + Math.sin(lt * 1.05) * 1.1) * enter;
            P.headY += (9 + Math.sin(lt * 1.5) * 1.3) * enter;
            P.legLRot += 5 * enter; P.legRRot -= 3 * enter;
            P.footL += 0.03 * enter;
            P.armLShoulder += 14 * enter; P.armRShoulder -= 14 * enter;
            break;
          }
          case 4: {  // 邊聽邊記：視線飄向左上、右手小幅來回像在寫字
            const write = Math.sin(lt * 5.4);
            P.headRot += (2.6 + Math.sin(lt * 0.68) * 1.2) * enter;
            P.headY += (4 + Math.sin(lt * 1.6) * 1.5) * enter;
            P.armRShoulder -= (30 + write * 5) * enter;
            P.armRElbow -= (22 + write * 9) * enter;
            P.handRFlex += (0.045 + Math.max(0, write) * 0.03) * enter;
            P.armLShoulder += 12 * enter;
            P.rootRot += Math.sin(lt * 0.85) * 0.9 * enter;
            P.scarfRot += Math.sin(lt * 1.3) * 2.4 * enter;
            break;
          }
          case 5: {  // 安靜凝視：幾乎不動，只有呼吸與極慢的左右擺，偶爾慢眨一次
            P.headRot += Math.sin(lt * 0.42) * 2.6 * enter;
            P.headX += Math.sin(lt * 0.42) * 3.4 * enter;
            P.headY += (2.5 + Math.sin(lt * 0.9) * 1) * enter;
            P.rootRot += Math.sin(lt * 0.42) * 0.5 * enter;
            P.sy += 0.004 * enter;
            P.armLShoulder += 5 * enter; P.armRShoulder -= 5 * enter;
            if (lt % 3.1 < dt && this.blinkPhase < 0) this.blinkPhase = 0;
            break;
          }
        }
      }

      // 思考中：歪頭往上看、身體輕輕晃，冒出三個點點；不帶任何情緒動作。
      // 點點在 (1005, 205)，也就是頭的框裡（頭佔 x 499..1037、y 42..576）——
      // 這是刻意的：它要疊在頭上像浮在腦袋前面的思緒，不是飄在旁邊的裝飾。
      // 點點本身是點描印象派畫的（fx_art.js），所以疊在毛上不會糊成一塊。
      if (this.thinking) {
        this._thinkT += dt;
        P.headRot += 3.5 + Math.sin(this._thinkT * 1.6) * 1.2;
        P.headY += 4;
        P.rootRot += Math.sin(this._thinkT * 0.8) * 0.9;
        P.sy += Math.sin(this._thinkT * 2.1) * 0.004;
        if (this._thinkT % 0.95 < dt) {
          this.fx.spawn("dots", { x: 1005, y: 205, vy: -34, life: 1.05, sway: 4 });
        }
      }

      // 待機行為疊加
      if (this.idle) this.idle.step(dt, P);

      // 使用者直接撫摸 / 拖曳，優先疊在待機與情緒動作之上
      if (this.interaction) this.interaction.step(dt, P);

      // 四肢與圍巾對情緒 / 重量做次級動作，讓身體不是僵硬貼圖
      if (this.emotion && this.emotionKey === "happy") {
        const wave = Math.sin(this.t * 5.2) * 2.4;
        P.armLShoulder += wave; P.armRShoulder -= wave;
      } else if (this.emotion && this.emotionKey === "excited") {
        const wave = Math.sin(this.t * 8.5) * 4.5;
        P.armLShoulder += wave; P.armRShoulder -= wave;
        P.legLRot -= wave * 0.18; P.legRRot += wave * 0.18;
      }
      P.scarfRot -= P.rootRot * 0.28;

      // 視線追蹤也會帶動頭部微小轉向，避免只有瞳孔移動。
      if (this.lookTarget && !this.thinking) {
        P.headRot += PET.clamp(this.lookTarget.x, -1, 1) * 1.7;
        P.headX += PET.clamp(this.lookTarget.x, -1, 1) * 4.5;
        P.headY += PET.clamp(this.lookTarget.y, -1, 1) * 2.5;
      }

      // 天氣環境姿勢：最後疊上去，情緒與待機都會帶著它
      const W = this.weatherPose;
      if (W) {
        if (W.lean) { P.rootRot += W.lean; P.headRot += W.lean * 0.35; }
        if (W.tremble) P.rootX += Math.sin(this.t * 31) * W.tremble;
        if (W.hunch) { P.sy -= 0.022 * W.hunch; P.sx += 0.016 * W.hunch; P.headY += 7 * W.hunch; }
        if (W.droop) { P.headY += 11 * W.droop; P.sy -= 0.03 * W.droop; P.rootY += 5 * W.droop; }
      }

      // 說話頭部彈跳
      P.headY += this.talkBob.step(dt) * 0.05;

      // 頭部擺動軟上限：所有來源(情緒/待機/拖曳)加總後統一收斂，脖子不再被拉長
      P.headRot = softLimit(P.headRot, HEAD_ROT_MAX);
      P.headX = softLimit(P.headX, HEAD_X_MAX);
      // 往上只收斂到溶接帶還有身體毛接得住的距離；往下沒有這個問題所以不限制
      if (P.headY < 0) P.headY = -softLimit(-P.headY, HEAD_Y_UP_MAX);

      // 彈簧趨近 + 套用
      // 任何一個通道變成 NaN 都會讓整顆頭的 transform 失效、畫面直接消失，
      // 所以在進彈簧前先擋掉；寧可少一個動作，也不要整隻熊不見。
      for (const k in P) {
        const v = P[k];
        this.springs[k].set(Number.isFinite(v) ? v : 0);
        this.pose[k] = this.springs[k].step(dt);
      }
      if (this.quality) this.quality.validate(P);
      const p = this.pose;
      PET.xform(this.rootG, {
        x: p.rootX, y: p.rootY, rot: p.rootRot,
        sx: 1 + p.sx, sy: 1 + p.sy, ox: ROOT_OX, oy: ROOT_OY,
      });
      PET.xform(this.headG, {
        x: p.headX, y: p.headY + this.headDrop, rot: p.headRot,
        sx: this.headScale, sy: this.headScale, ox: HEAD_OX, oy: HEAD_OY
      });

      // 頭壓圍巾：頭往下沉時身體上緣跟著壓縮，像下巴壓進圍巾裡
      const press = PET.clamp(p.headY, 0, 30) * 0.0016;
      const bsx = 1 + press * 0.35, bsy = 1 - press;
      PET.xform(this.bodyG, {
        x: 0, y: Math.sin(this.t * 1.6) * 0.35,
        rot: p.chestRot * 0.25,
        sx: bsx, sy: bsy, ox: ROOT_OX, oy: ROOT_OY,
      });

      // 圍巾布料：頭與身體的動作先合成一個「布想去的方向」，再讓軟彈簧慢慢追。
      // 追的過程就是延遲，追過頭再彈回來就是布料的回彈——圍巾因此會被頭帶著延伸出去，
      // 而不是整片跟著平移。剪力以下襬為支點（見 CLOTH_PIVOT），所以領口位移最大、
      // 下襬是 0，跟腿層之間永遠不會裂開。
      const leanTarget = PET.clamp(
        p.headX * 0.0011 + p.headRot * 0.0022 + p.rootRot * 0.0026
        + p.scarfRot * 0.0016 + p.rootX * 0.00035, -0.055, 0.055);
      const stretchTarget = PET.clamp(-p.headY * 0.0011 - p.sy * 0.18, -0.022, 0.03);
      this.clothLean.set(leanTarget);
      this.clothStretch.set(stretchTarget);
      p.clothLean = this.clothLean.step(dt);
      p.clothStretch = this.clothStretch.step(dt);
      p.clothPivot = CLOTH_PIVOT;
      this.body.apply(p);

      // 動態頸層：頭側錨點吃頭 transform、身側錨點吃身體 transform，
      // 貝茲連成白色封閉形，只描左右黑邊(線寬同輪廓)，永遠接著頭/身的輪廓線
      this._drawNeck(p, bsx, bsy);

      // 陰影隨跳躍
      const lift = PET.clamp(-p.rootY / 90, 0, 1);
      this.shadow.setAttribute("rx", 195 * (1 - lift * 0.35));
      this.shadow.setAttribute("opacity", (1 - lift * 0.55).toFixed(2));

      // 眨眼
      this._blink(dt);

      // 臉部彈簧 → 套用
      const fp = {};
      for (const k in this.faceS) fp[k] = this.faceS[k].step(dt);
      if (this.blinkPhase >= 0) {
        const u = this.blinkPhase;
        fp.eyeOpen *= u < 0.5 ? 1 - u * 2 : (u - 0.5) * 2;
      }
      this.face.apply(fp);

      this.fx.step(dt);
    }

    _drawNeck(p, bsx, bsy) {
      if (!this.neckOn) return;
      const rad = (p.headRot * Math.PI) / 180;
      const cos = Math.cos(rad), sin = Math.sin(rad);
      const hx = (pt, dy = 0) => {   // 頭空間 -> 世界（繞頸樞紐旋轉 + 平移）
        const dx0 = (pt.x - HEAD_OX) * this.headScale;
        const dy0 = (pt.y + dy - HEAD_OY) * this.headScale;
        return { x: HEAD_OX + dx0 * cos - dy0 * sin + p.headX,
                 y: HEAD_OY + dx0 * sin + dy0 * cos + p.headY + this.headDrop };
      };
      const bx = (pt, dy = 0) => {   // 身體空間 -> 世界（腳底原點縮放）
        return { x: ROOT_OX + (pt.x - ROOT_OX) * bsx,
                 y: ROOT_OY + (pt.y + dy - ROOT_OY) * bsy };
      };
      const A = this.neckA;
      const Lh = hx(A.hL), Rh = hx(A.hR);
      const Lb = bx(A.bL), Rb = bx(A.bR);
      // 貝茲控制點：沿頭側切線向下、身側切線向上 -> 黑邊與原輪廓相切連接
      const cL1 = hx(A.hL, 22), cL2 = bx(A.bL, -22);
      const cR1 = hx(A.hR, 22), cR2 = bx(A.bR, -22);
      // 上下緣往頭/身內部延伸(不描邊)，蓋住裁切邊的 AA
      const LhT = hx(A.hL, -12), RhT = hx(A.hR, -12);
      const LbB = bx(A.bL, 14), RbB = bx(A.bR, 14);
      const P = (o) => `${o.x.toFixed(1)} ${o.y.toFixed(1)}`;
      this.neckFill.setAttribute("d",
        `M ${P(LhT)} L ${P(Lh)} C ${P(cL1)} ${P(cL2)} ${P(Lb)} L ${P(LbB)}
         L ${P(RbB)} L ${P(Rb)} C ${P(cR2)} ${P(cR1)} ${P(Rh)} L ${P(RhT)} Z`);
      const S = this.neckLineA;
      const SLh = hx(S.hL), SRh = hx(S.hR);
      const SLb = bx(S.bL), SRb = bx(S.bR);
      const ScL1 = hx(S.hL, 22), ScL2 = bx(S.bL, -22);
      const ScR1 = hx(S.hR, 22), ScR2 = bx(S.bR, -22);
      this.neckSideL.setAttribute("d", `M ${P(SLh)} C ${P(ScL1)} ${P(ScL2)} ${P(SLb)}`);
      this.neckSideR.setAttribute("d", `M ${P(SRh)} C ${P(ScR1)} ${P(ScR2)} ${P(SRb)}`);
    }

    _blink(dt) {
      if (this.blinkPhase >= 0) {
        this.blinkPhase += dt / 0.16;
        if (this.blinkPhase >= 1) this.blinkPhase = -1;
        return;
      }
      this.blinkIn -= dt;
      if (this.blinkIn <= 0) {
        this.blinkIn = 2.2 + Math.random() * 3.2;
        if (this.faceS.eyeOpen.target > 0.5) this.blinkPhase = 0;
      }
    }
  };
})();
