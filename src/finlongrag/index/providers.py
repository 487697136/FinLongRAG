"""Embedding provider implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import numpy as np

from finlongrag.core.config import Settings, get_api_key
from finlongrag.index.vector import EmbeddingProvider


class EmbeddingProviderError(RuntimeError):
    """Raised when a configured embedding provider cannot produce embeddings."""


@dataclass(frozen=True)
class DashScopeEmbeddingProvider:
    """DashScope OpenAI-compatible embedding provider."""

    api_key: str
    model: str = "text-embedding-v4"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dimension: int = 1024
    batch_size: int = 16
    name: str = "dashscope"
    timeout_seconds: int = 120

    def embed(self, text: str) -> np.ndarray:
        vectors = self.embed_batch([text])
        return vectors[0] if len(vectors) else np.zeros(self.dimension, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        cleaned = [str(text or "") for text in texts]
        if not cleaned:
            return np.zeros((0, self.dimension), dtype=np.float32)
        rows: list[np.ndarray] = []
        for start in range(0, len(cleaned), max(1, self.batch_size)):
            rows.extend(self._embed_batch_once(cleaned[start : start + self.batch_size]))
        matrix = np.vstack(rows).astype(np.float32)
        if matrix.shape[1] != self.dimension:
            raise EmbeddingProviderError(
                f"embedding dimension mismatch from {self.model}: {matrix.shape[1]} != configured {self.dimension}"
            )
        return matrix

    def _embed_batch_once(self, texts: list[str]) -> list[np.ndarray]:
        # DashScope native API format
        payload: dict[str, Any] = {
            "model": self.model,
            "input": {
                "texts": texts
            }
        }
        # Complete URL: base + /text-embedding/text-embedding
        url = self.base_url.rstrip("/") + "/text-embedding/text-embedding"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError(f"DashScope embedding request failed: {exc}") from exc
        data = response.json()

        # DashScope returns output.embeddings
        output = data.get("output", {})
        items = output.get("embeddings")
        if not isinstance(items, list):
            raise EmbeddingProviderError(f"unexpected embedding response shape: {data}")

        vectors: list[np.ndarray] = []
        for item in items:
            raw_vector = item.get("embedding")
            if not isinstance(raw_vector, list):
                raise EmbeddingProviderError(f"missing embedding vector in response item: {item}")
            vector = np.asarray(raw_vector, dtype=np.float32)
            norm = float(np.linalg.norm(vector))
            vectors.append(vector / norm if norm > 0 else vector)
        if len(vectors) != len(texts):
            raise EmbeddingProviderError(f"embedding count mismatch: {len(vectors)} != {len(texts)}")
        return vectors


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    provider = settings.vector_embedding_provider.strip().lower()
    if provider in {"dashscope", "qwen"}:
        api_key = get_api_key()
        if not api_key:
            raise EmbeddingProviderError(
                "DASHSCOPE_API_KEY is required when FINLONGRAG_VECTOR_EMBEDDING_PROVIDER=dashscope"
            )
        # Base URL without /text-embedding, that gets appended in _embed_batch_once
        base_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings"
        return DashScopeEmbeddingProvider(
            api_key=api_key,
            model=settings.vector_embedding_model,
            base_url=base_url,
            dimension=settings.vector_dimension,
            batch_size=settings.vector_batch_size,
            timeout_seconds=settings.request_timeout_seconds,
        )
    raise EmbeddingProviderError(f"unsupported embedding provider: {settings.vector_embedding_provider}")
