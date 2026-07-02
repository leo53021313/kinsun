"""Citation 組裝。"""

from __future__ import annotations

from kinsun.rag.schemas import Citation, SearchResult


def assemble_citations(results: tuple[SearchResult, ...]) -> tuple[Citation, ...]:
    citations: list[Citation] = []
    seen: set[str] = set()
    for result in results:
        metadata = result.chunk.metadata
        if metadata.chunk_id in seen:
            continue
        seen.add(metadata.chunk_id)
        citations.append(
            Citation(
                source_id=metadata.source_id,
                title=metadata.title,
                publisher=metadata.publisher,
                url=metadata.source_url,
                chunk_id=metadata.chunk_id,
            )
        )
    return tuple(citations)
