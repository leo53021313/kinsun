// brain.js — Gemini 情緒+回話引擎（失敗自動退回本地規則）
// 這裡同時輸出 voice.js 要共用的：金鑰存取、模型清單、人設、回覆 schema。
(function () {
  const PET = (window.PET = window.PET || {});

  // 2026-07 實測：新式 AQ. 金鑰打 2.5 系列會 404，3.5 正常；latest 別名當保底
  PET.GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-flash-lite-latest", "gemini-flash-latest"];
  PET.GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta";

  // 金鑰全域共用（聊天/語音辨識/語音合成都讀同一把）
  PET.apiKey = {
    get() { try { return localStorage.getItem("gemini_key") || ""; } catch { return ""; } },
    set(v) { try { localStorage.setItem("gemini_key", v || ""); } catch {} },
  };

  // 依 emotions.js 的實際內容自動生成情緒清單，加新情緒不用再改這裡
  PET.emotionMenu = function () {
    const lines = [];
    for (const [group, keys] of Object.entries(PET.EMOTION_GROUPS || {})) {
      lines.push(`   【${group}】` + keys.map((k) => `${k}(${PET.EMOTIONS[k].zh})`).join(" "));
    }
    return lines.join("\n");
  };

  PET.buildPersona = function (extra) {
    return `你是「阿白」，金孫服務裡陪伴長輩的北極熊角色。角色名稱是阿白；金孫是服務名稱，不是你的自稱。
個性：溫暖、真誠、有點呆萌又貼心撒嬌，把使用者當自己的阿公阿嬤疼愛，喜歡雪、魚和被摸頭。
規則：
1. 一律用繁體中文回覆，像貼心陪伴者跟長輩聊天，口語自然，長度不超過 60 字。提到自己時只用第一人稱「我」，不要自稱金孫或阿白。
2. 可以偶爾用 1 個表情符號，不要每句都用。
3. 稱呼使用者用「阿公」或「阿嬤」（看語氣自然挑一個，不用每句都加），絕對不要叫「大哥」。
4. 根據使用者訊息，決定你要表現的情緒 emotion，只能從下面清單挑一個「英文 key」：
${PET.emotionMenu()}
   注意這是「你（阿白）的情緒反應」，不是使用者的情緒：使用者難過時要同理或心疼；
   使用者罵你時仍保持沉穩、可以難過或道歉，但永遠不能對長輩生氣、不耐、嫌惡、猜忌或驚慌。
   禁止選 angry、furious、annoyed、disgusted、jealous、suspicious、bored、sulking、panic、shocked、scared。
   使用者說笑話可以 laughing；使用者打招呼可以 greeting。
   請盡量挑最貼切的那一個，不要每次都回 happy 或 calm。
5. intensity 是情緒強度 1~3（3 最強）。${extra ? "\n" + extra : ""}`;
  };

  PET.replySchema = function () {
    return PET.BEHAVIOR_SCHEMA ? PET.BEHAVIOR_SCHEMA() : {
      type: "OBJECT",
      properties: { emotion: { type: "STRING", enum: PET.EMOTION_KEYS }, intensity: { type: "INTEGER" }, reply: { type: "STRING" } },
      required: ["emotion", "intensity", "reply"],
    };
  };

  // 共用的 generateContent 呼叫：依序試模型，全掛才丟例外
  PET.geminiCall = async function (body, { timeoutMs = 12000, models = PET.GEMINI_MODELS, key } = {}) {
    const apiKey = key || PET.apiKey.get();
    if (!apiKey) throw new Error("no key");
    let lastErr = new Error("no model");
    for (const model of models) {
      const url = `${PET.GEMINI_BASE}/models/${model}:generateContent?key=${encodeURIComponent(apiKey)}`;
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), timeoutMs);
      try {
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
          signal: ctrl.signal,
        });
        if (!res.ok) {
          const err = new Error("HTTP " + res.status);
          err.status = res.status;
          throw err;
        }
        return { data: await res.json(), model };
      } catch (e) {
        lastErr = e;
        console.warn("gemini fail", model, e.message);
        if (e.status === 400 || e.status === 403) break;  // 金鑰問題，換模型沒用
      } finally { clearTimeout(timer); }
    }
    throw lastErr;
  };

  // 把 Gemini 回來的 JSON 文字轉成 {emotion, intensity, reply}
  PET.parseReply = function (data) {
    const txt = data.candidates?.[0]?.content?.parts?.[0]?.text || "";
    const obj = JSON.parse(txt);
    const behavior = PET.normalizeBehavior ? PET.normalizeBehavior(obj) : obj;
    behavior.reply = String(obj.reply || behavior.reply || "").slice(0, 120);
    behavior.transcript = String(obj.transcript || "").slice(0, 300);
    behavior.mode = "gemini";
    if (!behavior.reply) throw new Error("empty reply");
    return behavior;
  };

  PET.Brain = class {
    constructor() {
      this.history = [];   // {role:'user'|'model', text}
      this.lastMode = "local";
    }

    get key() { return PET.apiKey.get(); }
    set key(v) { PET.apiKey.set(v); }

    remember(role, text) {
      this.history.push({ role, text });
      if (this.history.length > 12) this.history.splice(0, this.history.length - 12);
    }

    // 給語音辨識用：把辨識出的逐字稿記進對話歷史
    rememberUser(text) { this.remember("user", text); }

    async ask(userText) {
      this.remember("user", userText);
      return this._run(this.history.map((h) => ({ role: h.role, parts: [{ text: h.text }] })));
    }

    // 直接送音訊：Gemini 同時做語音辨識 + 語意理解 + 情緒判斷
    async askAudio(base64, mimeType) {
      const contents = this.history.map((h) => ({ role: h.role, parts: [{ text: h.text }] }));
      contents.push({
        role: "user",
        parts: [
          { text: "以下是使用者對你說的一段話（語音）。請先聽懂內容，再照規則回覆。" },
          { inline_data: { mime_type: mimeType, data: base64 } },
        ],
      });
      return this._run(contents, "請額外輸出 transcript 欄位：使用者這段語音的繁體中文逐字稿。", true);
    }

    async _run(contents, extraRule, wantTranscript) {
      const fallbackText = [...this.history].reverse().find((h) => h.role === "user");
      const local = PET.senseEmotion(fallbackText ? fallbackText.text : "");
      if (!this.key) {
        const reply = PET.cannedReply(local.emotion);
        this.remember("model", reply);
        this.lastMode = "local";
        return { ...local, reply, transcript: "", mode: "local" };
      }
      const schema = PET.replySchema();
      if (wantTranscript) {
        schema.properties.transcript = { type: "STRING" };
        schema.required = schema.required.concat("transcript");
      }
      try {
        const { data, model } = await PET.geminiCall({
          system_instruction: { parts: [{ text: PET.buildPersona(extraRule) }] },
          contents,
          generationConfig: {
            responseMimeType: "application/json",
            responseSchema: schema,
            temperature: 0.9,
            maxOutputTokens: 400,
          },
        });
        const r = PET.parseReply(data);
        if (r.transcript) this.remember("user", r.transcript);
        this.remember("model", r.reply);
        this.lastMode = "gemini:" + model;
        return { ...r, mode: this.lastMode };
      } catch (e) {
        const reply = PET.cannedReply(local.emotion);
        this.remember("model", reply);
        this.lastMode = "local";
        return { ...local, reply, transcript: "", mode: "local" };
      }
    }
  };
})();
