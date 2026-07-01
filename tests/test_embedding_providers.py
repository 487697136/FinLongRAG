"""Tests for embedding provider resilience."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from finlongrag.index.providers import DashScopeEmbeddingProvider, EmbeddingProviderError


def _embedding_response(count: int, *, dimension: int = 4) -> dict:
    return {
        "output": {
            "embeddings": [
                {"embedding": [1.0, 0.0, 0.0, 0.0][:dimension]}
                for _ in range(count)
            ]
        }
    }


def test_embed_batch_retries_transient_failures():
    provider = DashScopeEmbeddingProvider(
        api_key="test-key",
        dimension=4,
        batch_size=4,
        max_retries=2,
        base_url="https://example.com/api/v1/services/embeddings",
    )
    responses = [
        ConnectionError("server disconnected"),
        MagicMock(status_code=200, raise_for_status=MagicMock(), json=MagicMock(return_value=_embedding_response(2))),
    ]

    with patch("finlongrag.index.providers.get_api_key", return_value="test-key"), patch(
        "finlongrag.index.providers.requests.post",
        side_effect=responses,
    ) as post:
        vectors = provider.embed_batch(["a", "b"])

    assert post.call_count == 2
    assert vectors.shape == (2, 4)


def test_embed_batch_splits_batch_after_retry_exhaustion():
    provider = DashScopeEmbeddingProvider(
        api_key="test-key",
        dimension=4,
        batch_size=4,
        max_retries=0,
        base_url="https://example.com/api/v1/services/embeddings",
    )

    def _post(*_args, **_kwargs):
        payload = _kwargs.get("json") or {}
        texts = payload.get("input", {}).get("texts", [])
        if len(texts) > 1:
            raise ConnectionError("server disconnected")
        return MagicMock(
            status_code=200,
            raise_for_status=MagicMock(),
            json=MagicMock(return_value=_embedding_response(len(texts))),
        )

    with patch("finlongrag.index.providers.get_api_key", return_value="test-key"), patch(
        "finlongrag.index.providers.requests.post",
        side_effect=_post,
    ):
        vectors = provider.embed_batch(["a", "b"])

    assert vectors.shape == (2, 4)


def test_embed_batch_raises_when_single_item_fails():
    provider = DashScopeEmbeddingProvider(
        api_key="test-key",
        dimension=4,
        batch_size=4,
        max_retries=0,
        base_url="https://example.com/api/v1/services/embeddings",
    )

    with patch("finlongrag.index.providers.get_api_key", return_value="test-key"), patch(
        "finlongrag.index.providers.requests.post",
        side_effect=ConnectionError("server disconnected"),
    ), pytest.raises(EmbeddingProviderError):
        provider.embed_batch(["only-one"])
