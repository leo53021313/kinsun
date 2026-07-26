"""回覆切句（供 TTS 分段串流）：切在哪、不切在哪、以及切完仍是同一段話。"""

from __future__ import annotations

from kinsun.speech.chunking import MAX_CHUNKS, MIN_CHUNK_CHARS, split_for_speech


def test_splits_on_sentence_endings_keeping_the_punctuation():
    """標點要留在句尾——TTS 靠它決定語氣與停頓，切掉會讓每句都唸成平述句。"""
    assert split_for_speech("阿公今天早上好嗎。今天天氣不錯，要不要出去走走？") == [
        "阿公今天早上好嗎。",
        "今天天氣不錯，要不要出去走走？",
    ]


def test_a_single_sentence_stays_whole():
    assert split_for_speech("阿公您今天有沒有記得吃藥") == ["阿公您今天有沒有記得吃藥"]


def test_empty_text_yields_no_chunks():
    assert split_for_speech("") == []
    assert split_for_speech("   \n  ") == []


def test_short_fragments_merge_into_the_next_sentence():
    """太短的句子不獨立成段：每段都要付一次 TTS 固定成本（實測約 0.9 秒）＋
    一次上傳往返，為了三個字去付這些代價是賠本的。"""
    chunks = split_for_speech("好。阿公您今天過得怎麼樣？要不要出去走走？")
    assert all(len(c) >= MIN_CHUNK_CHARS or c is chunks[-1] for c in chunks)
    assert chunks[0].startswith("好。阿公")


def test_trailing_short_fragment_merges_backwards():
    """最後一段太短時往前併——後面已經沒有句子可以併了。"""
    chunks = split_for_speech("阿公您今天有沒有量血壓呢？好嗎？")
    assert chunks == ["阿公您今天有沒有量血壓呢？好嗎？"]


def test_chunk_count_is_capped():
    """段數有上限：每多一段就多一次往返，超過上限的句子併進最後一段。

    長輩聽到第一句的時間才是重點，後面切多細沒有額外好處。
    """
    text = "".join(f"這是第{i}句話喔阿公。" for i in range(12))
    chunks = split_for_speech(text)
    assert len(chunks) <= MAX_CHUNKS


def test_chunks_rejoin_to_the_original_text():
    """切完接回去必須與原文一字不差——長輩聽到的內容不可以因為分段而改變。"""
    for text in (
        "阿公早安喔。今天天氣不錯，要不要出去走走？記得多喝水。",
        "阿公您血壓高要少吃鹹的！醃漬品和罐頭湯都要節制。您中午那顆藥記得吃喔。",
        "好。",
        "沒有標點的一長串話語就這樣一直講下去也不換氣",
    ):
        assert "".join(split_for_speech(text)) == text.strip()


def test_newlines_are_split_points_too():
    """模型偶爾會用換行分段（prompt 禁 Markdown 但擋不住換行），也視為句界。"""
    assert split_for_speech("阿公今天早上好嗎\n今天要記得按時吃藥喔") == [
        "阿公今天早上好嗎\n",
        "今天要記得按時吃藥喔",
    ]
