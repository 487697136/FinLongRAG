"""Embedding provider implementations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import numpy as np
import requests

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
    max_retries: int = 2

    def embed(self, text: str) -> np.ndarray:
        vectors = self.embed_batch([text])
        return vectors[0] if len(vectors) else np.zeros(self.dimension, dtype=np.float32)

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        cleaned = [str(text or "") for text in texts]
        if not cleaned:
            return np.zeros((0, self.dimension), dtype=np.float32)
        rows: list[np.ndarray] = []
        for start in range(0, len(cleaned), max(1, self.batch_size)):
            rows.extend(self._embed_batch_resilient(cleaned[start : start + self.batch_size]))
        matrix = np.vstack(rows).astype(np.float32)
        if matrix.shape[1] != self.dimension:
            raise EmbeddingProviderError(
                f"embedding dimension mismatch from {self.model}: {matrix.shape[1]} != configured {self.dimension}"
            )
        return matrix

    def _embed_batch_resilient(self, texts: list[str]) -> list[np.ndarray]:
        try:
            return self._embed_batch_once(texts)
        except EmbeddingProviderError:
            if len(texts) <= 1:
                raise
            mid = len(texts) // 2
            return self._embed_batch_resilient(texts[:mid]) + self._embed_batch_resilient(texts[mid:])

    def _embed_batch_once(self, texts: list[str]) -> list[np.ndarray]:
        api_key = get_api_key() or self.api_key
        if not api_key:
            raise EmbeddingProviderError("DASHSCOPE_API_KEY is required for embedding requests")
        payload: dict[str, Any] = {
            "model": self.model,
            "input": {
                "texts": texts
            },
        }
        url = self.base_url.rstrip("/") + "/text-embedding/text-embedding"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_seconds)
                response.raise_for_status()
                data = response.json()
                return self._parse_embedding_response(data, texts)
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(1.5 * (attempt + 1))
        raise EmbeddingProviderError(f"DashScope embedding request failed: {last_error}") from last_error

    def _parse_embedding_response(self, data: dict[str, Any], texts: list[str]) -> list[np.ndarray]:
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
        base_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings"
        batch_size = min(settings.vector_batch_size, 10)
        return DashScopeEmbeddingProvider(
            api_key=api_key,
            model=settings.vector_embedding_model,
            base_url=base_url,
            dimension=settings.vector_dimension,
            batch_size=batch_size,
            timeout_seconds=settings.request_timeout_seconds,
            max_retries=settings.max_retries,
        )
    raise EmbeddingProviderError(f"unsupported embedding provider: {settings.vector_embedding_provider}")
