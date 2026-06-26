"""Embedding provider protocol and indexing text helpers."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from finlongrag.core.schema import Chunk
from finlongrag.index.tokenizer import tokenize_chunk_text


class EmbeddingProvider(Protocol):
    name: str
    dimension: int

    def embed(self, text: str) -> np.ndarray:
        ...

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        ...


def _embedding_text(chunk: Chunk, *, tokenizer_mode: str) -> str:
    structured = " ".join(str(item) for item in chunk.metadata.get("extra_index_fields", []))
    fields = [
        str(chunk.metadata.get("title") or ""),
        chunk.section,
        chunk.clause_id,
        chunk.text,
        " ".join(chunk.numbers),
        " ".join(chunk.dates),
        structured,
    ]
    raw = "\n".join(field for field in fields if field)
    tokens = tokenize_chunk_text(raw, [], mode=tokenizer_mode)
    return " ".join(tokens) if tokens else raw
