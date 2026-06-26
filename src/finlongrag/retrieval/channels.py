"""Generic retrieval channel contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from finlongrag.core.schema import Question, RetrievalResult
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.faiss_store import FaissVectorStore
from finlongrag.index.vector import EmbeddingProvider
from finlongrag.retrieval.fusion import reciprocal_rank_fusion


@dataclass
class SearchContext:
    question: Question
    queries: list[str]
    filter_doc_ids: set[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchChannelResult:
    channel: str
    results: list[RetrievalResult]
    metadata: dict[str, Any] = field(default_factory=dict)


class SearchChannel(Protocol):
    name: str
    priority: int

    def enabled(self, context: SearchContext) -> bool:
        ...

    def search(self, context: SearchContext) -> SearchChannelResult:
        ...


@dataclass
class BM25SearchChannel:
    index: BM25FIndex
    name: str = "bm25f"
    priority: int = 10

    def enabled(self, context: SearchContext) -> bool:
        return bool(context.queries)

    def search(self, context: SearchContext) -> SearchChannelResult:
        top_k_per_query = int(context.metadata.get("top_k_per_query", 20))
        fused_top_k = int(context.metadata.get("fused_top_k", 30))
        scoring_mode = str(context.metadata.get("scoring_mode", "bm25f"))
        source = str(context.metadata.get("source", "bm25f"))
        ranked_lists = [
            self.index.search(
                query,
                top_k=top_k_per_query,
                filter_doc_ids=context.filter_doc_ids,
                source=f"{source}:{self.name}",
                scoring_mode=scoring_mode,
            )
            for query in context.queries
            if query
        ]
        results = ranked_lists[0][:fused_top_k] if len(ranked_lists) == 1 else reciprocal_rank_fusion(ranked_lists, top_k=fused_top_k)
        return SearchChannelResult(
            channel=self.name,
            results=results,
            metadata={"queries": len(ranked_lists), "scoring_mode": scoring_mode},
        )


@dataclass
class FaissSearchChannel:
    store: FaissVectorStore
    provider: EmbeddingProvider
    name: str = "faiss"
    priority: int = 20

    def enabled(self, context: SearchContext) -> bool:
        return bool(context.queries)

    def search(self, context: SearchContext) -> SearchChannelResult:
        top_k_per_query = int(context.metadata.get("top_k_per_query", 20))
        fused_top_k = int(context.metadata.get("fused_top_k", 30))
        source = str(context.metadata.get("source", "vector"))
        ranked_lists = [
            self.store.search(
                query,
                provider=self.provider,
                top_k=top_k_per_query,
                filter_doc_ids=context.filter_doc_ids,
                source=f"{source}:{self.name}",
            )
            for query in context.queries
            if query
        ]
        results = ranked_lists[0][:fused_top_k] if len(ranked_lists) == 1 else reciprocal_rank_fusion(ranked_lists, top_k=fused_top_k)
        return SearchChannelResult(
            channel=self.name,
            results=results,
            metadata={
                "queries": len(ranked_lists),
                "provider": self.provider.name,
                "dimension": self.provider.dimension,
                "store": self.store.name,
            },
        )
