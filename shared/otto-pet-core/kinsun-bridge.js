// kinsun-bridge.js — React Native WebView 與 Otto renderer 的唯一接縫。
(function () {
  const PET = window.PET;
  const mount = document.getElementById("petMount");
  const pet = (window.kinsunBear = new PET.Pet(mount));
  const prefersReducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  if (prefersReducedMotion) pet.motionEnabled = false;
  else new PET.Idle(pet);
  const talker = new PET.TalkDriver(pet);
  let lastSequence = -1;

  function notify(type, detail) {
    const payload = JSON.stringify({ version: 1, type, detail });
    // App：React Native WebView。
    if (window.ReactNativeWebView) {
      window.ReactNativeWebView.postMessage(payload);
      return;
    }
    // 網頁版：一般瀏覽器的 iframe。targetOrigin 用 "*" 是必要的——iframe 帶
    // sandbox 時是不透明來源，取不到父層 origin；訊息內容只有 ready 與
    // invalid-message，不含任何機密，且父層以 `event.source === iframe.contentWindow`
    // 驗證來源。判斷 `window.parent !== window` 是為了不在 App 那條路徑上自己
    // 送給自己（RN WebView 是頂層文件，parent 就是自己）。
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(payload, "*");
    }
  }

  /**
   * 依情緒推出身體動作意圖（手勢、姿態、頭部擺動）。
   *
   * ⚠️ 用 `setMotionIntent` 而不是 `applyBehavior`／`beginBehavior`：後兩者會走
   * `BehaviorController.begin()`，而那支會依 `eye_focus`（預設 `"user"`）呼叫
   * `pet.lookAt(0, 0)`——每講一句話就把使用者的視線追蹤歸零，阿白會在「看著你」與
   * 「看正前方」之間跳動。`setMotionIntent` 只設意圖、不碰視線。
   *
   * ⚠️ 手勢由 `AnimationStateMachine._sampleGesture` 取樣，而它**只在 `emotion`／
   * `action` 狀態跑**（`speaking` 走的是另一條通用律動）——所以手勢是在阿白**講完
   * 之後**演出來的，由 `talkEnd()` 依 `pet.behavior.hand_gesture` 切進去。
   */
  function applyMotionIntent(emotion, intensity) {
    if (!PET.behaviorFromEmotion) return;
    pet.setMotionIntent(PET.behaviorFromEmotion(emotion, intensity));
  }

  /**
   * 講完話之後，讓手勢演完再回待機（毫秒）。
   *
   * ⚠️ **沒有這道保護，手勢等於沒做**：手勢只在 `action`／`emotion` 狀態取樣，由
   * `talkEnd()` 在最後一個字之後切進去；而對講機是「音檔播完 → 佇列空 → 立刻送
   * idle」，兩件事幾乎同時發生——實測收到 idle 後右肩擺幅由 22.5 掉到 1.99（只剩
   * 呼吸），長輩看不到任何手勢。
   *
   * 1.2 秒：實測 1 秒就跑完約兩個半揮手週期，足夠看清楚；再長會讓狀態帶已經說
   * 「準備好了」而阿白還在揮手。⚠️ 這只延後**回待機**——長輩按麥克風（listening）
   * 或任何其他狀態一律立即生效並取消保護，不會讓聆聽姿勢慢半拍。
   */
  const GESTURE_HOLD_MS = 1200;
  /**
   * 打招呼演完再回待機（毫秒）。比 `GESTURE_HOLD_MS` 長：那是句尾的餘韻，這是一段
   * 完整的演出——`greeting` 情緒本身的剪輯就有 1.6 秒，加上揮手要一個完整的來回。
   */
  const GREET_MS = 2600;
  let gestureHoldTimer = null;

  function clearGestureHold() {
    if (gestureHoldTimer !== null) {
      clearTimeout(gestureHoldTimer);
      gestureHoldTimer = null;
    }
  }

  function stopTransientState() {
    talker.stop();
    if (pet.listening) pet.listen(false);
    if (pet.thinking) pet.think(false);
  }

  function applyCommand(command) {
    if (!command || command.version !== 1) return;

    // 視線：指標每動一下就是一則，刻意不吃 sequence（理由見 shared/ottoBridge.ts
    // 的 OttoLookCommand）。⚠️ 兩軸要嘛都是有限數、要嘛一起回正——只有一軸的視線
    // 會讓阿白歪向一個沒人在的方向。
    if (command.type === "look") {
      const x = Number(command.x);
      const y = Number(command.y);
      if (Number.isFinite(x) && Number.isFinite(y)) {
        pet.lookAt(Math.min(1, Math.max(-1, x)), Math.min(1, Math.max(-1, y)));
        // 指標在動就代表人還在：把打盹中的阿白叫醒（`Idle` 不存在時是 no-op）。
        pet.userActivity();
      } else {
        // ⚠️ 回正用 `lookAt(0, 0)` 而不是 `lookAt(null)`：後者只清掉 `lookTarget`
        // （頭會回正），但**不碰瞳孔的彈簧目標**（見 pet.js 的 lookAt）——眼珠會停
        // 在最後看的那個方向斜著不回來，直到下一次情緒或待機動作剛好重設臉部。
        // (0, 0) 兩件事都做到：頭部位移乘以 0 等同沒有視線，瞳孔確實回到正中。
        pet.lookAt(0, 0);
      }
      return;
    }

    // 長輩點了浮出來的小道具。`Idle.tap()` 自己擋重複（一次待機只認第一下），
    // 且在 reduced-motion 下 `pet.idle` 根本不存在——兩種情形都不需要外層知道。
    if (command.type === "tap") {
      if (pet.idle) pet.idle.tap();
      return;
    }

    // 進畫面打招呼：揮手＋「打招呼」情緒，演完自己回待機。
    //
    // ⚠️ 走與手勢保護同一顆計時器：長輩在打招呼演到一半就按了麥克風時，`sync` 分支
    // 的 `clearGestureHold()` 會把它取消——聆聽姿勢不會等這段演完才開始。
    if (command.type === "greet") {
      clearGestureHold();
      stopTransientState();
      applyMotionIntent("greeting", 2);
      pet.setEmotion("greeting", { intensity: 2 });
      gestureHoldTimer = setTimeout(function () {
        gestureHoldTimer = null;
        pet.backToIdle();
      }, GREET_MS);
      return;
    }

    if (command.type !== "sync") return;
    if (!Number.isInteger(command.sequence) || command.sequence <= lastSequence) return;
    if (!["idle", "listening", "thinking", "speaking", "error"].includes(command.state)) return;
    lastSequence = command.sequence;
    // 任何一個新狀態都比「把上一句的手勢演完」重要——長輩已經在做下一件事了。
    clearGestureHold();
    stopTransientState();
    document.body.classList.toggle("is-error", command.state === "error");

    if (command.state === "listening") {
      pet.backToIdle();
      pet.listen(true);
      return;
    }
    if (command.state === "thinking") {
      pet.backToIdle();
      pet.think(true);
      return;
    }
    if (command.state === "speaking") {
      const text = String(command.text || "").slice(0, 500);
      const sensed = command.emotion
        ? { emotion: PET.sanitizeEmotion(command.emotion), intensity: 2 }
        : PET.senseEmotion(text);
      // ⚠️ 順序：意圖要先設。`setEmotion` 內部會 `stateMachine.set("emotion",
      // { intent: this.behavior })`，晚一步的話那一輪帶進去的還是上一句的意圖。
      applyMotionIntent(sensed.emotion, sensed.intensity);
      pet.setEmotion(sensed.emotion, { intensity: sensed.intensity });
      talker.talk(text, { durationMs: Number(command.durationMs) || 0 });
      return;
    }
    if (command.state === "error") {
      pet.backToIdle();
      applyMotionIntent("apologetic", 1);
      pet.setEmotion("apologetic", { intensity: 1 });
      return;
    }

    // 回待機。⚠️ 阿白剛講完、手勢正在演的話（`talkEnd()` 依 `hand_gesture` 切進
    // `action`）先讓它演完——見 GESTURE_HOLD_MS 上方說明。`stopTransientState()`
    // 已經在上面呼叫過，此處只剩「什麼時候真的回待機」這一件事。
    if (pet.stateMachine && pet.stateMachine.state === "action") {
      gestureHoldTimer = setTimeout(function () {
        gestureHoldTimer = null;
        pet.backToIdle();
      }, GESTURE_HOLD_MS);
      return;
    }
    pet.backToIdle();
  }

  function receive(event) {
    try {
      applyCommand(JSON.parse(event.data));
    } catch {
      notify("invalid-message");
    }
  }

  // 待機浮出可點道具時通知外層來畫（renderer 自己沒有道具的樣式，見 renderer.css）。
  //
  // ⚠️ **道具的按鈕畫在外層、不畫在 renderer 裡**：iframe 是 `pointer-events: none`
  // 且不給 `allow-same-origin`，畫在裡面的東西點不到；更重要的是可點的東西必須進得了
  // 輔助科技的樹，而整個 iframe 對外是 `aria-hidden` 的裝飾層。
  //
  // ⚠️ 沒有訂閱者的那一端（App）不畫按鈕，於是沒有道具可點——事件照發但被忽略，
  // 這是「道具只在網頁版」最小的實作方式，不需要另一組開關指令。
  if (pet.idle) {
    pet.on("idleTap", (detail) => {
      if (!detail || detail.state !== "show" || !detail.tap) {
        notify("idle-prop", null);
        return;
      }
      notify("idle-prop", {
        key: detail.key,
        zh: detail.zh,
        icon: detail.tap.icon,
        label: detail.tap.label,
        x: detail.tap.x,
        y: detail.tap.y,
      });
    });
  }

  // iOS 使用 window，部分 Android WebView 版本使用 document；sequence 會擋重複投遞。
  window.addEventListener("message", receive);
  document.addEventListener("message", receive);

  (function drive() {
    let last = performance.now();
    (function loop(now) {
      const dt = Math.min((now - last) / 1000, 0.06);
      talker.step(dt);
      last = now;
      requestAnimationFrame(loop);
    })(last);
  })();

  notify("ready");
})();
