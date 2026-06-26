"""Index build helpers."""

from __future__ import annotations

from pathlib import Path

from finlongrag.core.io import read_jsonl
from finlongrag.core.schema import Chunk
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.document import DocumentIndex


def load_chunks(path: Path) -> list[Chunk]:
    return [Chunk.from_dict(row) for row in read_jsonl(path)]


def build_chunk_index(chunks_path: Path, index_path: Path, tokenizer_mode: str = "mixed") -> BM25FIndex:
    chunks = load_chunks(chunks_path)
    index = BM25FIndex.build(chunks, tokenizer_mode=tokenizer_mode)
    index.save(index_path)
    return index


def build_document_index(chunks_path: Path, index_path: Path, tokenizer_mode: str = "mixed") -> DocumentIndex:
    chunks = load_chunks(chunks_path)
    index = DocumentIndex.build(chunks, tokenizer_mode=tokenizer_mode)
    index.save(index_path)
    return index

