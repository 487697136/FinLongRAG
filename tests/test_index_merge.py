"""Tests for global index merge."""

from __future__ import annotations

from pathlib import Path

from dataclasses import replace

from finlongrag.core.config import Settings
from finlongrag.core.schema import Chunk
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.merge import merge_global_indexes
from finlongrag.storage.knowledge_repository import KnowledgeBaseRecord


class _FakeKnowledgeRepository:
    def __init__(self, chunks_by_kb: dict[str, list[Chunk]]) -> None:
        self._chunks_by_kb = chunks_by_kb

    def list_knowledge_bases(self, *, limit: int = 100) -> list[KnowledgeBaseRecord]:
        return [
            KnowledgeBaseRecord(
                kb_id=kb_id,
                name=f"KB {kb_id}",
                description="",
                metadata={},
            )
            for kb_id in self._chunks_by_kb
        ][:limit]

    def load_chunks(self, *, kb_id: str | None = None, limit: int | None = None) -> list[Chunk]:
        if kb_id is None:
            chunks: list[Chunk] = []
            for items in self._chunks_by_kb.values():
                chunks.extend(items)
            return chunks[: limit or None]
        return list(self._chunks_by_kb.get(kb_id, []))[: limit or None]


def _chunk(chunk_id: str, kb_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=f"doc_{kb_id}",
        domain="test",
        text=text,
        metadata={"kb_id": kb_id},
    )


def test_merge_global_indexes_writes_global_files(tmp_path: Path) -> None:
    settings = Settings.from_file()
    settings = replace(settings, index_dir=tmp_path / "index")
    repo = _FakeKnowledgeRepository(
        {
            "kb1": [_chunk("c1", "kb1", "营业收入 100 亿元")],
            "kb2": [_chunk("c2", "kb2", "净利润 20 亿元")],
        }
    )

    result = merge_global_indexes(settings, repo)

    assert result["status"] == "ok"
    assert result["chunks"] == 2
    assert (tmp_path / "index" / "bm25_index_global.pkl").exists()
    assert (tmp_path / "index" / "document_index_global.pkl").exists()

    loaded = BM25FIndex.load(tmp_path / "index" / "bm25_index_global.pkl")
    hits = loaded.search("营业收入", top_k=3)
    assert hits
    assert hits[0].chunk_id == "c1"


def test_merge_global_indexes_clears_stale_files_when_no_chunks(tmp_path: Path) -> None:
    settings = Settings.from_file()
    settings = replace(settings, index_dir=tmp_path / "index")
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    global_bm25 = settings.index_dir / "bm25_index_global.pkl"
    global_doc = settings.index_dir / "document_index_global.pkl"
    global_bm25.write_bytes(b"stale")
    global_doc.write_bytes(b"stale")

    repo = _FakeKnowledgeRepository({})
    result = merge_global_indexes(settings, repo)

    assert result["status"] == "cleared"
    assert not global_bm25.exists()
    assert not global_doc.exists()
