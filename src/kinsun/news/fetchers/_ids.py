"""新聞項目 id 產生：以來源＋網址雜湊出決定性 id。

決定性（而非隨機 uuid）是刻意的：同一篇文章每天被爬到都算出同一個 id，
save() 的 upsert 語意才會就地更新既有列，而不是每天多插入一筆重複的新聞。
"""

from __future__ import annotations

import hashlib


def make_news_item_id(source_id: str, url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{source_id}:{digest}"
