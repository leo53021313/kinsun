"""簡單且可測試的文字 chunker。"""

from __future__ import annotations

from dataclasses import replace

from kinsun.rag.schemas import ChunkMetadata, DocumentChunk


def chunk_text(
    text: str,
    metadata: ChunkMetadata,
    *,
    max_chars: int = 480,
) -> tuple[DocumentChunk, ...]:
    if max_chars < 80:
        raise ValueError("max_chars 不可小於 80")

    paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
    chunks: list[DocumentChunk] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(_make_chunk(current, metadata, len(chunks)))
        current = paragraph
    if current:
        chunks.append(_make_chunk(current, metadata, len(chunks)))
    return tuple(chunks)


def _make_chunk(text: str, metadata: ChunkMetadata, index: int) -> DocumentChunk:
    chunk_metadata = replace(metadata, chunk_id=f"{metadata.document_id}#chunk-{index + 1}")
    return DocumentChunk(text=text, metadata=chunk_metadata)
