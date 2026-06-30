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
        kb_id = context.metadata.get("kb_id")
        kb_ids = context.metadata.get("kb_ids")
        if not kb_id and isinstance(kb_ids, list) and len(kb_ids) == 1:
            kb_id = str(kb_ids[0])

        # 多知识库融合：分别检索每个库，确保多样性
        if kb_ids and len(kb_ids) > 1:
            per_kb_top_k = max(10, top_k_per_query // len(kb_ids))
            all_results = []
            for kid in kb_ids:
                for query in context.queries:
                    if not query:
                        continue
                    results = self.index.search(
                        query,
                        top_k=per_kb_top_k,
                        filter_doc_ids=context.filter_doc_ids,
                        source=f"{source}:{self.name}",
                        scoring_mode=scoring_mode,
                        kb_id=kid,  # 单独检索每个库
                    )
                    all_results.extend(results)
            # 去重并按分数排序
            seen = set()
            unique_results = []
            for r in sorted(all_results, key=lambda x: x.score, reverse=True):
                key = (r.chunk_id, r.doc_id)
                if key not in seen:
                    seen.add(key)
                    unique_results.append(r)
            results = unique_results[:fused_top_k]
        else:
            # 单知识库或全局检索：原有逻辑
            ranked_lists = [
                self.index.search(
                    query,
                    top_k=top_k_per_query,
                    filter_doc_ids=context.filter_doc_ids,
                    source=f"{source}:{self.name}",
                    scoring_mode=scoring_mode,
                    kb_id=kb_id,
                    kb_ids=kb_ids,
                )
                for query in context.queries
                if query
            ]
            results = ranked_lists[0][:fused_top_k] if len(ranked_lists) == 1 else reciprocal_rank_fusion(ranked_lists, top_k=fused_top_k)

        return SearchChannelResult(
            channel=self.name,
            results=results,
            metadata={"queries": len(context.queries), "scoring_mode": scoring_mode},
        )


@dataclass
class FaissSearchChannel:
    store: FaissVectorStore
    provider: EmbeddingProvider
    name: str = "faiss"
    priority: int = 20

    def enabled(self, context: SearchContext) -> bool:
        if not context.metadata.get("enable_vector_retrieval", True):
            return False
        return bool(context.queries)

    def search(self, context: SearchContext) -> SearchChannelResult:
        top_k_per_query = int(context.metadata.get("top_k_per_query", 20))
        fused_top_k = int(context.metadata.get("fused_top_k", 30))
        source = str(context.metadata.get("source", "vector"))
        kb_id = context.metadata.get("kb_id")
        kb_ids = context.metadata.get("kb_ids")
        if not kb_id and isinstance(kb_ids, list) and len(kb_ids) == 1:
            kb_id = str(kb_ids[0])

        # 多知识库融合：分别检索每个库
        if kb_ids and len(kb_ids) > 1:
            from finlongrag.index.faiss_store import FaissVectorStore
            per_kb_top_k = max(10, top_k_per_query // len(kb_ids))
            all_results = []
            for kid in kb_ids:
                store = FaissVectorStore(
                    index_root=self.store.index_root,
                    dimension=self.store.dimension,
                    tokenizer_mode=self.store.tokenizer_mode,
                    kb_id=kid,
                )
                for query in context.queries:
                    if not query:
                        continue
                    results = store.search(
                        query,
                        provider=self.provider,
                        top_k=per_kb_top_k,
                        filter_doc_ids=context.filter_doc_ids,
                        source=f"{source}:{self.name}",
                    )
                    all_results.extend(results)
            # 去重并按分数排序
            seen = set()
            unique_results = []
            for r in sorted(all_results, key=lambda x: x.score, reverse=True):
                key = (r.chunk_id, r.doc_id)
                if key not in seen:
                    seen.add(key)
                    unique_results.append(r)
            results = unique_results[:fused_top_k]
        else:
            # 单知识库或全局检索
            store = self.store
            if kb_id and store.kb_id != kb_id:
                from finlongrag.index.faiss_store import FaissVectorStore
                store = FaissVectorStore(
                    index_root=store.index_root,
                    dimension=store.dimension,
                    tokenizer_mode=store.tokenizer_mode,
                    kb_id=kb_id,
                )

            ranked_lists = [
                store.search(
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
                "queries": len(context.queries),
                "provider": self.provider.name,
                "dimension": self.provider.dimension,
                "store": self.store.name,
                "kb_id": kb_id,
                "kb_ids": kb_ids,
            },
        )
