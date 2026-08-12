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
    if (!command || command.version !== 1 || command.type !== "sync") return;
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
