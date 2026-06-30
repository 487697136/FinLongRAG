"""Merge per-KB chunk indexes into global BM25 / Document indexes."""

from __future__ import annotations

import logging
from typing import Any

from finlongrag.core.config import Settings
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.document import DocumentIndex
from finlongrag.storage.knowledge_repository import KnowledgeRepository

logger = logging.getLogger(__name__)


def merge_global_indexes(
    settings: Settings,
    repository: KnowledgeRepository,
    *,
    kb_limit: int = 10_000,
) -> dict[str, Any]:
    """Rebuild merged BM25 + Document indexes across all knowledge bases."""
    kbs = repository.list_knowledge_bases(limit=kb_limit)
    all_chunks = []
    for kb in kbs:
        all_chunks.extend(repository.load_chunks(kb_id=kb.kb_id))

    global_bm25_path = settings.index_dir / "bm25_index_global.pkl"
    global_doc_path = settings.index_dir / "document_index_global.pkl"

    if not all_chunks:
        cleared = []
        for path in (global_bm25_path, global_doc_path):
            if path.exists():
                path.unlink()
                cleared.append(path.name)
        logger.info("Global index merge cleared stale files: %s", cleared or "none")
        return {
            "status": "cleared",
            "reason": "no_chunks",
            "chunks": 0,
            "knowledge_bases": len(kbs),
            "cleared_files": cleared,
        }

    settings.index_dir.mkdir(parents=True, exist_ok=True)

    bm25 = BM25FIndex.build(all_chunks, tokenizer_mode=settings.tokenizer_mode)
    doc_index = DocumentIndex.build(all_chunks, tokenizer_mode=settings.tokenizer_mode)
    bm25.save(global_bm25_path)
    doc_index.save(global_doc_path)

    logger.info("Merged global indexes: %s chunks from %s knowledge bases.", len(all_chunks), len(kbs))
    return {
        "status": "ok",
        "chunks": len(all_chunks),
        "knowledge_bases": len(kbs),
        "bm25_index_path": str(global_bm25_path),
        "document_index_path": str(global_doc_path),
    }
