"""Local FAISS vector storage and search."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import faiss
import numpy as np

from finlongrag.core.schema import Chunk, RetrievalResult
from finlongrag.index.providers import create_embedding_provider
from finlongrag.index.vector import EmbeddingProvider, _embedding_text


class VectorStore(Protocol):
    name: str

    def replace_embeddings(self, *, kb_id: str, chunks: list[Chunk], provider: EmbeddingProvider) -> dict:
        ...

    def search(
        self,
        query: str,
        *,
        provider: EmbeddingProvider,
        top_k: int,
        filter_doc_ids: set[str] | None = None,
        source: str = "vector:faiss",
    ) -> list[RetrievalResult]:
        ...


@dataclass(frozen=True)
class FaissVectorStore:
    index_root: Path
    dimension: int
    tokenizer_mode: str = "mixed"
    kb_id: str | None = None
    name: str = "faiss"

    def __post_init__(self) -> None:
        if self.dimension <= 0:
            raise ValueError("vector dimension must be positive")

    def replace_embeddings(self, *, kb_id: str, chunks: list[Chunk], provider: EmbeddingProvider) -> dict:
        if provider.dimension != self.dimension:
            raise ValueError(f"provider dimension mismatch: {provider.dimension} != {self.dimension}")
        if not chunks:
            raise ValueError("no chunks available for FAISS embedding")

        texts = [_embedding_text(chunk, tokenizer_mode=self.tokenizer_mode) for chunk in chunks]
        vectors = _normalize(provider.embed_batch(texts))
        if vectors.shape != (len(chunks), self.dimension):
            raise ValueError(f"unexpected embedding shape: {vectors.shape}")

        index = faiss.IndexFlatIP(self.dimension)
        index.add(vectors)

        target_dir = self._kb_dir(kb_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        index_path = target_dir / "index.faiss"
        metadata_path = target_dir / "metadata.jsonl"
        manifest_path = target_dir / "manifest.json"

        _write_faiss_index(index, index_path)
        rows = [_chunk_row(chunk, text, provider) for chunk, text in zip(chunks, texts, strict=True)]
        with metadata_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        manifest = {
            "store": self.name,
            "kb_id": kb_id,
            "provider": provider.name,
            "model": str(getattr(provider, "model", provider.name)),
            "dimension": provider.dimension,
            "chunks": len(chunks),
            "index_path": str(index_path),
            "metadata_path": str(metadata_path),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest

    def search(
        self,
        query: str,
        *,
        provider: EmbeddingProvider,
        top_k: int,
        filter_doc_ids: set[str] | None = None,
        source: str = "vector:faiss",
    ) -> list[RetrievalResult]:
        if not query.strip():
            return []
        indexes = self._candidate_indexes()
        if not indexes:
            return []
        query_vector = _normalize(provider.embed_batch([query]))
        results: list[RetrievalResult] = []
        for index_dir in indexes:
            index_path = index_dir / "index.faiss"
            metadata_path = index_dir / "metadata.jsonl"
            if not index_path.exists() or not metadata_path.exists():
                continue
            rows = _read_jsonl(metadata_path)
            if not rows:
                continue
            index = _read_faiss_index(index_path)
            limit = min(max(int(top_k), 1), len(rows))
            scores, ids = index.search(query_vector, limit)
            for score, row_id in zip(scores[0], ids[0], strict=True):
                if row_id < 0 or row_id >= len(rows):
                    continue
                row = rows[int(row_id)]
                doc_id = str(row.get("doc_id") or "")
                if filter_doc_ids and doc_id not in filter_doc_ids:
                    continue
                results.append(_result_from_row(row, score=float(score), query=query, source=source))
        results.sort(key=lambda item: item.score, reverse=True)
        return results[:top_k]

    def _candidate_indexes(self) -> list[Path]:
        faiss_root = self.index_root / "faiss"
        if self.kb_id:
            return [self._kb_dir(self.kb_id)]
        if not faiss_root.exists():
            return []
        return sorted(path for path in faiss_root.iterdir() if path.is_dir())

    def _kb_dir(self, kb_id: str) -> Path:
        return self.index_root / "faiss" / _safe_id(kb_id)


def create_configured_vector_store(settings, *, kb_id: str | None = None) -> FaissVectorStore | None:
    if settings.vector_store.strip().lower() != "faiss":
        return None
    return FaissVectorStore(
        index_root=settings.index_dir,
        dimension=settings.vector_dimension,
        tokenizer_mode=settings.tokenizer_mode,
        kb_id=kb_id,
    )


def build_faiss_embeddings(settings, *, kb_id: str, chunks: list[Chunk]) -> dict:
    store = create_configured_vector_store(settings, kb_id=kb_id)
    if store is None:
        raise ValueError("FAISS store requires FINLONGRAG_VECTOR_STORE=faiss")
    provider = create_embedding_provider(settings)
    return store.replace_embeddings(kb_id=kb_id, chunks=chunks, provider=provider)


def _chunk_row(chunk: Chunk, embedding_text: str, provider: EmbeddingProvider) -> dict[str, Any]:
    return {
        "chunk": chunk.to_dict(),
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "domain": chunk.domain,
        "evidence_text": chunk.text,
        "embedding_text_hash": hashlib.sha256(embedding_text.encode("utf-8")).hexdigest(),
        "provider": provider.name,
        "model": str(getattr(provider, "model", provider.name)),
        "dimension": provider.dimension,
    }


def _result_from_row(row: dict[str, Any], *, score: float, query: str, source: str) -> RetrievalResult:
    chunk_data = dict(row.get("chunk") or {})
    metadata = dict(chunk_data.get("metadata") or {})
    return RetrievalResult(
        chunk_id=str(row.get("chunk_id") or chunk_data.get("chunk_id") or ""),
        doc_id=str(row.get("doc_id") or chunk_data.get("doc_id") or ""),
        domain=str(row.get("domain") or chunk_data.get("domain") or ""),
        evidence_text=str(row.get("evidence_text") or chunk_data.get("text") or ""),
        score=score,
        source=source,
        query=query,
        metadata={
            **metadata,
            "page": chunk_data.get("page"),
            "section": chunk_data.get("section") or "",
            "clause_id": chunk_data.get("clause_id") or "",
            "numbers": list(chunk_data.get("numbers") or []),
            "dates": list(chunk_data.get("dates") or []),
            "tables": list(chunk_data.get("tables") or []),
            "vector_provider": row.get("provider"),
            "vector_model": row.get("model"),
            "vector_dimension": row.get("dimension"),
            "vector_store": "faiss",
        },
    )


def _normalize(vectors: np.ndarray) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2:
        raise ValueError(f"expected 2D embedding matrix, got shape {matrix.shape}")
    faiss.normalize_L2(matrix)
    return matrix


def _write_faiss_index(index, path: Path) -> None:
    serialized = faiss.serialize_index(index)
    path.write_bytes(np.asarray(serialized, dtype=np.uint8).tobytes())


def _read_faiss_index(path: Path):
    data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    return faiss.deserialize_index(data)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def _safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip()) or "default"
