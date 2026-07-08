# ADR-007: 語音服務自架 DGX（ASR＝Breeze-ASR-26、TTS＝CosyVoice 3）

> **狀態:** 已接受 | **日期:** 2026-07-08 | **決策者:** Leo（批次重新確認；台語微調＝D-01）

## 1. 背景與問題

- **上下文**: 語音是長輩唯一主互動方式；需要國台語 ASR 與自然的 TTS（含聲音複製）。
- **問題**: 雲端語音服務按量計費且台語支援差；團隊有 DGX Spark（GPU）可自架。
- **驅動因素/約束**: 「位置無關」原則——重模型以網路服務提供，應用層只是 client（環境變數配 endpoint）。

## 2. 考量的選項

- **自架 DGX**：Breeze-ASR-26（已驗證國台語辨識）＋CosyVoice 3（zero-shot 聲音複製）。
- **雲端 ASR/TTS**（Google／Azure）：台語品質不可控、費用隨量、隱私外傳面擴大。

## 3. 決策

**選擇**: 自架 `services/asr`＋`services/tts` 於 DGX，應用層經 `speech/asr.py`、`speech/tts.py` client 呼叫（backend 可切 mock 供離線開發）。

**理由**: 台語是差異化核心（D-01）；DGX 已實機驗證通過；語音資料不出自架環境。

## 4. 後果

- **正面**: 台語路線可控——TTS 微調進行中（另專案清洗語料，CosyVoice 3 vs VoxCPM2 對比後擇一，D-01）。
- **負面**: DGX 單點（校內機器）；demo 當天依賴網路連通性（→ 14_部署循環議備援）。
- **重新評估觸發**: DGX 不可用；台語微調兩模型皆不達標時。
