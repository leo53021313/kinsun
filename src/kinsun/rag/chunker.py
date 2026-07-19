"""簡單且可測試的文字 chunker。"""

from __future__ import annotations

import re
from dataclasses import replace

from kinsun.rag.schemas import ChunkMetadata, DocumentChunk
from kinsun.rag.text_cleaner import clean_text

_BOUNDARY_RE = re.compile(r"(?<=[。！？；!?;])|\n+")


def chunk_text(
    text: str,
    metadata: ChunkMetadata,
    *,
    max_chars: int = 480,
    overlap_chars: int = 80,
) -> tuple[DocumentChunk, ...]:
    if max_chars < 80:
        raise ValueError("max_chars 不可小於 80")

    cleaned = clean_text(text)
    parts = [part.strip() for part in _BOUNDARY_RE.split(cleaned) if part.strip()]
    chunks: list[DocumentChunk] = []
    current = ""
    for part in parts:
        if len(part) > max_chars:
            if current:
                chunks.append(_make_chunk(current, metadata, len(chunks)))
                current = ""
            for piece in _hard_split(part, max_chars=max_chars, overlap_chars=overlap_chars):
                chunks.append(_make_chunk(piece, metadata, len(chunks)))
            continue
        candidate = f"{current}\n{part}".strip() if current else part
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(_make_chunk(current, metadata, len(chunks)))
        current = part
    if current:
        chunks.append(_make_chunk(current, metadata, len(chunks)))
    return tuple(chunks)


def _hard_split(text: str, *, max_chars: int, overlap_chars: int) -> tuple[str, ...]:
    overlap = min(max(overlap_chars, 0), max_chars // 4)
    step = max_chars - overlap
    return tuple(text[start : start + max_chars] for start in range(0, len(text), step))


def _make_chunk(text: str, metadata: ChunkMetadata, index: int) -> DocumentChunk:
    chunk_metadata = replace(metadata, chunk_id=f"{metadata.document_id}#chunk-{index + 1}")
    return DocumentChunk(text=text, metadata=chunk_metadata)
