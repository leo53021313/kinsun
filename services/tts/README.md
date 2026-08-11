# TTS 服務（CosyVoice 3）— DGX 端

文字轉語音（繁體國語漢字 → 語音）推論服務。**僅在 DGX Spark 執行**（需 GPU 與 `cosyvoice`／`torch`），不屬於應用層、不進開發機的測試套件。

> 狀態：**已於 DGX 實機驗證**（2026-07-02，GB10 / aarch64 / CUDA 13）。CosyVoice 3 zero-shot
> 合成、wav→m4a、healthz、併發控制、`X-Duration-Ms` 皆通過；單句 RTF≈0.7（快於即時），
> 輸出 m4a 經 `ffprobe` 確認為 AAC/24kHz/單聲道且時長與標頭一致。
> 目前為**國語**語音；台語版本待後續只換本服務的合成實作，契約不變、應用層不動。
> 參考語音（金孫聲音）尚待正式定調——驗證時暫用 CosyVoice 內附 `asset/zero_shot_prompt.wav`。

## 與應用層的契約

| 項目 | 內容 |
|------|------|
| 路徑 | `POST /synthesize` |
| 請求 | JSON `{"text": "<繁體國語漢字>", "elder_id"?: "...", "prompt_audio_url"?: "...", "prompt_text"?: "..."}`；後三個欄位選填，用於長輩客製化聲音複製（2026-07-30，見下方「長輩客製化聲音」） |
| 回應 | body 為 **m4a（AAC）bytes**、`Content-Type: audio/mp4`、header `X-Duration-Ms: <int>`（合成語音毫秒數） |
| 健康檢查 | `GET /healthz` → `{"status": "ok"｜"degraded", "model_loaded": <bool>, "stuck_workers": <int>}`；`degraded`＝有合成逾時後放生的執行緒，需重啟行程回收 |
| 過載 | 等候請求數超過 `TTS_MAX_CONCURRENCY + TTS_MAX_QUEUE` → 回 503 |
| 逾時 | 合成超過 `TTS_SYNTH_TIMEOUT_SECONDS` → 回 504（`synthesis_timeout`） |
| 呼叫端 | `kinsun.speech.tts.DgxTtsClient`（已實作，見 [tts.py](../../src/kinsun/speech/tts.py)） |

> `DgxTtsClient` 會把回應包成 `TtsResult(text=text, audio=<bytes>, duration_ms=<int>)`，
> 介面與既有 `TTSClient.synthesize(text, *, voice=None) -> TtsResult` 一致。

## 長輩客製化聲音（聲音克隆，2026-07-30）

每位長輩可設定專屬的參考語音（例如家人的聲音），取代全域預設的金孫聲音，設定檔存在應用層
`voice_profiles` 表（見 [`voice_profiles/store.py`](../../src/kinsun/voice_profiles/store.py)）。

- 應用層 `VoicePipeline` 依 `elder_id` 查出該長輩生效中的 `VoiceProfile`（若有），組成
  `VoiceReference` 傳給 `DgxTtsClient.synthesize`；`DgxTtsClient` 會把 `elder_id`／
  `prompt_audio_url`／`prompt_text` 一併塞進 `/synthesize` 的 JSON body。
- 本服務收到請求後：
  1. 沒帶 `elder_id` → 沿用全域 `TTS_PROMPT_WAV`／`TTS_PROMPT_TEXT`（與今天行為一致）。
  2. 帶 `elder_id` 且本機已快取該長輩的參考音檔 → 直接用快取，不重新下載。
  3. 帶 `elder_id` 但快取沒有、且同時帶 `prompt_audio_url`／`prompt_text` → 下載一次
     （標準庫 `urllib.request`，不新增第三方依賴）存進 `TTS_VOICE_CACHE_DIR`，之後同一
     `elder_id` 重複請求就免下載。
  4. 帶 `elder_id` 但快取沒有、也沒帶 `prompt_audio_url` → 退回全域預設聲音（容錯，不炸請求）。
- 快取為簡單 FIFO（非 LRU），上限 `TTS_VOICE_CACHE_SIZE`，超過時淘汰最舊的一位長輩。
- 已知限制：`prompt_audio_url` 目前是 Supabase 簽章 URL，會過期；過期後若快取又剛好失效
  會下載失敗，需重新註冊該長輩的參考語音（詳見 `docs/dev/05_架構與設計.md` §8.1）。

## 逾時與降級（2026-08-09）

`TTS_MAX_CONCURRENCY` 預設為 1（只有一顆 GPU），意即**任何一個卡死的請求都會佔走
唯一的併發名額**，之後所有長輩都拿不到名額——整台服務不再產出語音，而且不會自行恢復。

三處新增的逾時，性質**刻意不同**：

| 位置 | 逾時後 | 資源真的回收嗎 |
|---|---|---|
| ffmpeg 轉檔 | 子行程被 SIGKILL | ✅ 完全回收 |
| 參考音檔下載 | socket 逾時、拋例外 | ✅ 完全回收 |
| **模型合成** | 讓出併發名額、回 504 | ⚠️ **執行緒仍在背景跑** |

⚠️ **模型合成那道不是完全的復原。** 合成跑在 threadpool，而 Python 殺不掉執行緒——
逾時只能讓等待的協程放棄、把名額讓出來，那條工作者仍在跑、仍握著 GPU。

因此每次逾時都會累加 `stuck_workers`，並讓 `/healthz` 轉為 `degraded`：
放生的執行緒只能靠**重啟行程**回收，維運需要看得見這件事。先前 healthz 只回報模型
載入與否，於是服務癱瘓時它依然回 `ok`，監控全綠、只有長輩發現金孫不說話了。

`TTS_SYNTH_TIMEOUT_SECONDS` 預設 120 秒刻意寬鬆：GPU 下長回覆約 8 秒，但 GPU 被佔滿時
本服務會降級跑 CPU（RTF 13～16，同樣的話要 60～70 秒），照 GPU 抓會讓降級模式每句都逾時。
長輩那端另有自己的 30 秒上限（應用層 `TTS_TIMEOUT_SECONDS`）；這裡的目的不是控制長輩
等多久，而是不讓卡死的請求永久佔住名額。

## 參考語音的錄製準則（2026-08-09 實測）

同時適用於**全域金孫聲音**（`TTS_PROMPT_WAV`）與**長輩客製化聲音**（家屬錄的那段）。
第 1～4 點皆為在 DGX 8012 實機 A/B 測出來的，不是推測；第 5 點為尚未解決的已知限制。

### 1. 內容必須包含「阿嬤」

**「嬤」是罕用字，模型念不準**——實測聽起來是一聲且氣音蓋掉，幾乎聽不出這個字。
而「阿嬤」是本系統出現頻率最高的稱呼。

參考語音裡只要有人用台灣口音講過「阿嬤」，合成時就會照著念。
對照實驗（**同一位說話者**，只差參考語音有沒有這個詞）證實有效，故與說話者無關。

同理可推廣到其他罕用字：**長輩的名字、地名、方言詞，想念對就放進參考語音**。

⚠️ 同音字替換（阿罵／阿媽）**行不通**：實測「罵」的四聲不夠力、還會破壞後續斷句；
「媽」發音正確但不是台灣人講的那個音。wetext 前端也沒有標註發音的介面
（`set_lang_type('pinyinvg')` 只在 `ttsfrd` 前端可用）。

### 2. 說話者的表現力會直接傳遞

**語調平的人錄出來的金孫也是平的。** 對照實驗（**同一份稿子**、只換人錄）差異明顯。

這決定產品的「人格」——挑錄音者時，講話有起伏、語氣自然的人比音色好聽更重要。

### 3. 長度 10～15 秒，不要更短

太短會讓**輸出長度不穩定**。實測同一句 16 字的話各跑三次：

| 參考語音 | 三次的產出長度 | 穩定度 |
|---|---|---|
| 15.7 秒 / 56 字 | 5.12 / 5.12 / 4.52 秒 | 穩 |
| 7 秒 / 21 字 | 4.72 / 6.04 / 7.16 秒 | 不穩 |
| 4 秒 / 9 字 | 6.92 / 6.72 / 5.04 秒（另有一次 11.88 秒） | 不穩 |

### 4. 逐字稿別遠長於典型合成句

CosyVoice 會對「合成文字比參考逐字稿短」發出 `this may lead to bad performance` 警告。
實測**聽不出品質差異，但速度明顯變慢**：

| 合成文字 | 56 字參考的 RTF | 30 字參考的 RTF |
|---|---|---|
| 6 字 | 1.50 | 0.64 |
| 16 字 | 0.81 | 0.54 |
| 40 字 | 0.65 | 0.51 |

本系統回覆上限 30 字、分段每段至少 8 字，故實際落在 8～30 字區間。
**參考逐字稿 30 字左右**即可兼顧穩定與速度；56 字會讓短回覆的合成慢一倍。

### 5. 已知限制：語尾助詞「喔」會隨機卡頓（2026-08-09，尚未解決）

合成到「喔」時，**約五次有四次**會在該字前後出現不自然的停頓或收尾感。

實測（同一段參考語音、同一組句子各跑兩次）：

| 句型 | 卡頓 |
|---|---|
| 「阿嬤記得吃藥喔，吃完再去睡午覺」（喔在句中） | 一次卡、一次不卡 |
| 「阿嬤記得要吃藥喔」（喔在句尾） | 兩次都卡 |

**同一句話兩次結果不同，故位置不是決定因素——是隨機不穩。**
原先「參考語音只示範過句尾的喔，模型才不會念句中的」這個假設已被此實測推翻。

「喔」在長輩照護的語域極常出現（要吃藥喔、多喝水喔、早點睡喔），值得後續處理。

**尚未驗證的推測**（供接手者參考，不要當成結論）：現行參考語音的唯一一個「喔」
位於整段錄音的最末尾，錄音者很可能講完即按停、尾音被切掉；模型學到殘缺樣本，
因而每次重現都不穩。驗證方式＝重錄一段讓「喔」出現兩次（一次句中、一次句尾），
且**最後一字之後留白一秒再停止錄音**，再與現行版本各合成六次比較卡頓次數。

## 部署（DGX）

CosyVoice 3 非 pip 套件：需 clone [FunAudioLLM/CosyVoice](https://github.com/FunAudioLLM/CosyVoice) repo
（含 `cosyvoice/` 套件與 `third_party/Matcha-TTS`），並把模型權重放本機目錄。服務啟動時會把
`TTS_COSY_DIR` 與 `TTS_MATCHA_DIR` 加入 `sys.path`，並以 `AutoModel` 依模型目錄自動判別為 CosyVoice3。

```bash
# 在 DGX 的 cosyvoice 環境（含 torch/torchaudio/soundfile 與 CosyVoice repo 依賴）
pip install -r services/tts/requirements.txt   # fastapi/uvicorn/soundfile；torch 等依 CosyVoice repo
export TTS_MODEL_ID=/abs/path/to/Fun-CosyVoice3-0.5B-2512   # 本機權重目錄
export TTS_COSY_DIR=/abs/path/to/CosyVoice                  # CosyVoice repo
export TTS_PROMPT_WAV=/abs/path/to/prompt.wav               # 金孫參考語音
export TTS_PROMPT_TEXT='參考語音的逐字稿'
export TTS_PRELOAD=1
uvicorn services.tts.server:app --host 0.0.0.0 --port 8002
```

**系統需求：** `ffmpeg`（DGX 端把模型輸出的 wav 轉成 m4a／AAC，應用層跨平台不裝 ffmpeg）。
mp4/m4a 的 `moov` atom 需可 seek 的輸出，故服務走可 seek 的暫存檔轉檔再讀回（非 `pipe`）。

**aarch64 注意：** torchaudio 的 load/save 會走 torchcodec（`.so` 載不起來），服務以 `soundfile`
取代之。zero-shot 逐字稿內部會加 instruct 前綴 `You are a helpful assistant.<|endofprompt|>`，
否則 LLM 會立刻 EOS、產不出語音。

**環境變數：**

| 環境變數 | 預設 | 用途 |
|---|---|---|
| `TTS_MODEL_ID` | `FunAudioLLM/Fun-CosyVoice3-0.5B-2512` | 模型 id 或本機權重目錄（本機優先，免下載） |
| `TTS_COSY_DIR` | 空（必填） | CosyVoice repo 目錄（加入 `sys.path`），缺會載入時明確報錯 |
| `TTS_MATCHA_DIR` | 空 | Matcha-TTS 目錄，留空＝`{TTS_COSY_DIR}/third_party/Matcha-TTS` |
| `TTS_PROMPT_WAV` | 空（必填） | 參考音檔路徑（金孫聲音，5–15 秒乾淨人聲），缺會啟動時明確報錯 |
| `TTS_PROMPT_TEXT` | 空（必填） | `TTS_PROMPT_WAV` 的逐字稿 |
| `TTS_MAX_CONCURRENCY` | `1` | 同時處理的合成請求數（threadpool + semaphore） |
| `TTS_MAX_QUEUE` | `8` | 等候佇列上限，超過回 503（`overloaded`） |
| `TTS_API_KEY` | 空 | 共用金鑰（✅ D-56）：設定後驗 `X-Api-Key`（錯誤回 401）；留空＝內網不驗 |
| `TTS_MAX_TEXT_CHARS` | `1000` | 合成文字長度上限；超過回 413、缺 text 回 400（✅ D-26） |
| `TTS_PRELOAD` | `0` | 設 `1` 於服務啟動（lifespan）即載入模型，預設延遲載入（大小寫不敏感） |
| `TTS_VOICE_CACHE_DIR` | 系統暫存目錄 | 長輩客製化參考音檔下載後的本機快取位置 |
| `TTS_VOICE_CACHE_SIZE` | `20` | 最多同時快取幾位長輩的客製化參考音檔（FIFO 淘汰） |
| `TTS_SYNTH_TIMEOUT_SECONDS` | `120` | 單一請求的合成上限；逾時回 504 並讓出併發名額（見下方「逾時與降級」） |
| `TTS_VOICE_DOWNLOAD_TIMEOUT_SECONDS` | `15` | 參考音檔下載逾時 |
| `TTS_FFMPEG_TIMEOUT_SECONDS` | `30` | wav→m4a 轉檔逾時（子行程，殺得掉） |

## 接到應用層

於應用層 `.env` 設定：

```dotenv
TTS_BACKEND=dgx
TTS_ENDPOINT=http://<dgx-host>:8002/synthesize
```

`TTS_BACKEND=dgx` 時 `build_tts_client` 會建立 `DgxTtsClient`；缺 `TTS_ENDPOINT` 會在組裝期報錯。
語音回覆另需設定音檔發佈（`SUPABASE_URL`／`SUPABASE_SERVICE_KEY`／`AUDIO_BUCKET`，見專案根 [README.md](../../README.md)）。

## 待辦（於 DGX 實機驗證）

- [x] 選定 TTS 模型：**CosyVoice 3**（`FunAudioLLM/Fun-CosyVoice3-0.5B-2512`），已實作並實機驗證 zero-shot 合成。
      台語版本待後續替換 `server.py` 的合成實作（契約不變）。
- [x] 在 aarch64 + CUDA 上實際裝起 CosyVoice 3 並跑通（torch 2.12.1+cu130、`AutoModel`、`soundfile` 取代 torchaudio、instruct 前綴）。
- [x] 併發與健康檢查（`GET /healthz`）——threadpool + semaphore + 佇列上限 503。
- [x] 應用層新增 `TTS_BACKEND`／`TTS_ENDPOINT` 設定與 `DgxTtsClient`，取代 `TextBubbleTts`——已實作（`build_tts_client`）。
- [x] wav→m4a 轉檔（可 seek 暫存檔）並經 `ffprobe` 確認為合法 m4a；`X-Duration-Ms` 與實際時長一致。
- [x] 長輩客製化聲音複製（2026-07-30）：`/synthesize` 支援選填 `elder_id`／`prompt_audio_url`／
      `prompt_text`，本機快取＋向下相容（見上方「長輩客製化聲音」）；應用層 `voice_profiles`
      表與 `VoicePipeline` 串接已實作。家屬上傳／同意 UX 尚未建置（設計中，非本次範圍）。
- [ ] **（交付 Leo）** 錄製並定調正式**金孫參考語音**——作為缺客製化設定檔時長輩聽到的
      全域預設聲音。**這是團隊層級的決定，不是純技術工項**：參考語音的說話者表現力會
      直接傳給金孫（見上方準則第 2 條實測），等於決定產品的「人格」；且錄音者需知情同意
      自己的聲音將成為系統對所有長輩說話的聲音。

      技術面的準備已完成，錄音者照著做即可（四條準則詳見上方「參考語音的錄製準則」）：
      - 12～15 秒、講話語調有起伏的人
      - 內容含「阿嬤」至少兩次
      - 逐字稿 30 字左右
      - **「喔」出現兩次（一次句中、一次句尾），且最後一字後留白一秒再停止錄音**
        ——這是為了同時驗證上方已知限制第 5 條的推測
      - 建議稿：「阿嬤您好，我是小明。記得吃飽飯再吃藥喔，胃才不會不舒服。阿嬤也要多喝水，保重身體喔。」

      驗收方式：新舊參考各合成同一組句子六次，比對「喔」的卡頓次數與輸出長度穩定度。

- [x] ~~以真 LINE 帳號驗 `AudioMessage` 播放~~ → **N/A（2026-08-11）**：前端已收斂為純網頁端，
      LINE 通道擱置（見 `docs/dev` 前端決策），本項不再適用。模型端 m4a 已確認可播，
      網頁端播放亦已於 `/demo` 對講機端到端驗證。
- [x] 服務端逐請求 timeout（2026-08-09）：合成／下載／轉檔三處各有上限，逾時讓出併發名額並回 504；
      模型合成的執行緒殺不掉，故累計 `stuck_workers` 並由 `/healthz` 回報 `degraded`（見上方「逾時與降級」）。
