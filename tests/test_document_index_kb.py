"""Tests for KB-scoped document-level blind routing."""

from __future__ import annotations

from finlongrag.core.schema import Chunk
from finlongrag.index.document import DocumentIndex


def _doc_chunk(doc_id: str, kb_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"{kb_id}:{doc_id}:1",
        doc_id=doc_id,
        domain="financial_reports",
        text=text,
        metadata={"kb_id": kb_id, "title": doc_id},
    )


def test_document_index_search_respects_kb_id_filter():
    chunks = [
        _doc_chunk("d1", "kb1", "营业收入 100 亿元"),
        _doc_chunk("d2", "kb2", "营业收入 200 亿元"),
    ]
    doc_index = DocumentIndex.build(chunks)
    hits = doc_index.search_doc_ids("营业收入", top_k=5, kb_id="kb1")
    assert hits == ["d1"]


def test_document_index_search_respects_kb_ids_filter():
    chunks = [
        _doc_chunk("d1", "kb1", "净利润 10 亿元"),
        _doc_chunk("d2", "kb2", "净利润 20 亿元"),
        _doc_chunk("d3", "kb3", "净利润 30 亿元"),
    ]
    doc_index = DocumentIndex.build(chunks)
    hits = doc_index.search_doc_ids("净利润", top_k=5, kb_ids=["kb1", "kb3"])
    assert set(hits) == {"d1", "d3"}
