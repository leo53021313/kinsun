"""把回覆切成可逐段合成的句子，讓長輩早一點聽到第一個字。

為什麼要切（2026-07-26 延遲實測）：TTS 的耗時是 **0.9 秒固定成本 ＋ 每字 0.10 秒**，
而回覆字數生產 p50 為 39 字、p90 為 70 字——整段合成完才送出，長輩就得等 5～8 秒。
只合成第一句先送出，第一個字提早約 2～4 秒到耳朵裡。

⚠️ 為什麼不改成「分段平行合成」（那樣後端自己接回一個檔、App 完全不用改）：實測過，
行不通。TTS 服務併發拉到 3 之後，39 字回覆平行 5.12s vs 整段 5.83s、64 字回覆平行
8.26s vs 整段 **7.62s**（更慢）。瓶頸是 GPU——三個 CosyVoice 推論在同一顆 GB10 上
互相搶資源，那 0.9 秒固定成本並沒有被攤掉，反而付了三次。故唯一有效的路是真串流。
"""

from __future__ import annotations

import hashlib
import re

# 段數上限：每多一段就多一次「TTS 固定成本＋上傳往返」，而長輩只在乎第一句多快到。
MAX_CHUNKS = 4
# 一段至少要這麼多字，否則併進鄰段。門檻由實測推導，不是拍腦袋：
#   合成 N 字耗時 ≈ 0.9 + 0.10N 秒；N 字唸出來的語音長度 ≈ N / 4.6 秒（實測 38 字→8.26 秒）。
# 要讓「這一段播放的時間」蓋得住「下一段合成的時間」，才不會播到一半卡住等下一段：
#   N / 4.6 ≥ 0.9 + 0.10N  →  0.117N ≥ 0.9  →  N ≥ 7.7
# 故取 8。低於此的段落獨立送出，只會換來播放中間的空白。
MIN_CHUNK_CHARS = 8

# 句界＝中文句末標點或換行。逗號**不切**：逗號處切開會讓 TTS 把半句唸成完整句，
# 語氣塌掉；prompt 已要求「最多兩三句」，句號級的切點就夠用了。
_SENTENCE = re.compile(r"[^。！？!?\n]*(?:[。！？!?\n]+|$)")


def _raw_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE.findall(text) if s]


def split_for_speech(text: str) -> list[str]:
    """切成逐段合成的句子；接回去與 `text.strip()` 一字不差。

    空白字串回空清單（沒有東西可唸）。合併規則：太短的段往後併，併不動（已是最後
    一段）就往前併；段數超過上限時，多出來的全部併進最後一段。
    """
    stripped = text.strip()
    if not stripped:
        return []
    sentences = _raw_sentences(stripped)
    if not sentences:
        return []

    merged: list[str] = []
    buffer = ""
    for sentence in sentences:
        buffer += sentence
        if len(buffer.strip()) >= MIN_CHUNK_CHARS:
            merged.append(buffer)
            buffer = ""
    if buffer:  # 尾巴太短：往前併，沒有前段就自成一段
        if merged:
            merged[-1] += buffer
        else:
            merged.append(buffer)

    if len(merged) > MAX_CHUNKS:
        head, tail = merged[: MAX_CHUNKS - 1], merged[MAX_CHUNKS - 1 :]
        merged = [*head, "".join(tail)]
    return merged


def reply_digest(reply: str) -> str:
    """回覆內容的短雜湊，用來確認後續段落取的是同一輪的回覆。

    分段串流是跨請求的：第一段隨回合回應送出，其餘由前端逐段取。中間長輩若又講了
    一句，「最近一則金孫回覆」就換人了——沒有這道確認，前端會把新回覆的第二句接在
    舊回覆後面播。伺服器不留狀態（回覆全文本來就已寫進 `turns`），故用雜湊比對。

    ⚠️ 一定要餵**真正的回覆文字**（`TtsResult.text`），不可餵投遞層的顯示字串：
    `ASR_DEBUG_SHOW_TRANSCRIPT=true` 時顯示字串會多出「辨識：…／回復：…」的前綴，
    與寫進 `turns` 的內容不同，雜湊對不上就變成每一段都被判為過期（2026-07-26
    實機驗證踩到）。
    """
    return hashlib.sha1(reply.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
