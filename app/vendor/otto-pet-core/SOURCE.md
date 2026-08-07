# Otto pet-core 納入說明

來源：`Polar Bear/Otto's Polar Bear/pet-core/`，MIT License（Copyright 2026 Mas-000）。

正式 App 僅載入角色渲染所需的向量素材、骨架／臉部／情緒動畫、注音 viseme、
本地 sentiment 與 `kinsun-bridge.js`。`brain.js` 保留作為上游人設與 schema 參考，
但不會被 renderer HTML 載入。

刻意未納入正式 runtime：`main.js`、`voice.js`、`speech.js`、`conversation.js`、
`weather.js`、`weather_art.js`、`food.js`、`scene.js`、`interactions.js`。這些模組會建立
第二套麥克風／LLM／TTS／定位／外部網路流程，與金孫 App 已有的後端、安全與權限契約衝突。

產物由 `app/scripts/build-otto-renderer.mjs` 產生；請勿直接修改
`app/assets/otto/renderer.html`。
