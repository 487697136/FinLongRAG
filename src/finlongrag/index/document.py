"""Document-level sparse index for blind retrieval and product QA."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from finlongrag.core.schema import Chunk
from finlongrag.index.bm25 import BM25FIndex


class DocumentIndex:
    def __init__(self, index: BM25FIndex) -> None:
        self.index = index

    @classmethod
    def build(cls, chunks: list[Chunk], tokenizer_mode: str = "mixed", max_doc_chars: int = 30000) -> DocumentIndex:
        by_doc: dict[str, list[Chunk]] = defaultdict(list)
        for chunk in chunks:
            by_doc[chunk.doc_id].append(chunk)
        doc_chunks: list[Chunk] = []
        for doc_id, items in sorted(by_doc.items()):
            first = items[0]
            title = str(first.metadata.get("title") or doc_id)
            parts = [title]
            for item in items:
                parts.append(" ".join([item.section, item.clause_id, item.text, " ".join(item.metadata.get("extra_index_fields", []))]))
                if sum(len(part) for part in parts) >= max_doc_chars:
                    break
            doc_chunks.append(
                Chunk(
                    chunk_id=f"doc::{doc_id}",
                    doc_id=doc_id,
                    domain=first.domain,
                    text="\n".join(parts)[:max_doc_chars],
                    page=None,
                    section="document",
                    metadata={
                        "title": title,
                        "doc_level": True,
                        "kb_id": first.metadata.get("kb_id"),
                    },
                )
            )
        return cls(BM25FIndex.build(doc_chunks, tokenizer_mode=tokenizer_mode))

    def search_doc_ids(
        self,
        query: str,
        top_k: int = 8,
        domain: str | None = None,
        kb_id: str | None = None,
        kb_ids: list[str] | None = None,
    ) -> list[str]:
        filter_doc_ids = self._scoped_doc_ids(domain=domain, kb_id=kb_id, kb_ids=kb_ids)
        return [item.doc_id for item in self.index.search(query, top_k=top_k, filter_doc_ids=filter_doc_ids)]

    def _scoped_doc_ids(
        self,
        *,
        domain: str | None,
        kb_id: str | None,
        kb_ids: list[str] | None,
    ) -> set[str] | None:
        if not domain and not kb_id and not kb_ids:
            return None
        candidates = self.index.chunks
        if domain:
            candidates = [chunk for chunk in candidates if chunk.domain == domain]
        if kb_ids:
            kb_id_set = set(kb_ids)
            candidates = [chunk for chunk in candidates if chunk.metadata.get("kb_id") in kb_id_set]
        elif kb_id:
            candidates = [chunk for chunk in candidates if chunk.metadata.get("kb_id") == kb_id]
        if not candidates:
            return set()
        return {chunk.doc_id for chunk in candidates}

    def save(self, path: Path) -> None:
        self.index.save(path)

    @classmethod
    def load(cls, path: Path) -> DocumentIndex:
        return cls(BM25FIndex.load(path))

