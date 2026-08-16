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

    if (command.type !== "sync") return;
    if (!Number.isInteger(command.sequence) || command.sequence <= lastSequence) return;
    if (!["idle", "listening", "thinking", "speaking", "error"].includes(command.state)) return;
    lastSequence = command.sequence;
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
      pet.setEmotion(sensed.emotion, { intensity: sensed.intensity });
      talker.talk(text, { durationMs: Number(command.durationMs) || 0 });
      return;
    }
    if (command.state === "error") {
      pet.backToIdle();
      pet.setEmotion("apologetic", { intensity: 1 });
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
