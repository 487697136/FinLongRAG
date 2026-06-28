"""Retrieval orchestration."""

from __future__ import annotations

from finlongrag.core.schema import Question, RetrievalResult
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.document import DocumentIndex
from finlongrag.index.faiss_store import FaissVectorStore
from finlongrag.index.vector import EmbeddingProvider
from finlongrag.retrieval.channels import (
    BM25SearchChannel,
    FaissSearchChannel,
    SearchChannel,
    SearchContext,
)
from finlongrag.retrieval.fusion import reciprocal_rank_fusion
from finlongrag.retrieval.queries import build_question_queries, question_with_options


class Retriever:
    def __init__(
        self,
        index: BM25FIndex,
        doc_index: DocumentIndex | None = None,
        *,
        top_k_per_query: int = 24,
        fused_top_k: int = 40,
        blind_top_docs: int = 8,
        scoring_mode: str = "bm25f",
        vector_provider: EmbeddingProvider | None = None,
        vector_store: FaissVectorStore | None = None,
        bm25_channel_weight: float = 1.0,
        vector_channel_weight: float = 0.45,
    ) -> None:
        self.index = index
        self.doc_index = doc_index
        self.vector_provider = vector_provider
        self.vector_store = vector_store
        self.top_k_per_query = top_k_per_query
        self.fused_top_k = fused_top_k
        self.blind_top_docs = blind_top_docs
        self.scoring_mode = scoring_mode
        self.channels: list[SearchChannel] = [BM25SearchChannel(index)]
        self.channel_weights = {"bm25f": bm25_channel_weight, "faiss": vector_channel_weight}
        if vector_store is not None and vector_provider is not None:
            self.channels.append(FaissSearchChannel(vector_store, vector_provider))
        self.channels.sort(key=lambda channel: channel.priority)

    def retrieve_question(self, question: Question, *, restrict_to_doc_ids: bool = True) -> list[RetrievalResult]:
        filter_doc_ids = self.candidate_doc_filter(question, restrict_to_doc_ids=restrict_to_doc_ids)
        return self._search_channels(
            question,
            build_question_queries(question),
            filter_doc_ids=filter_doc_ids,
            source="question",
        )

    def retrieve_queries(
        self,
        queries: list[str],
        *,
        filter_doc_ids: set[str] | None,
        top_k_per_query: int | None = None,
        fused_top_k: int | None = None,
        source: str = "claim_bm25f",
        metadata: dict | None = None,
    ) -> list[RetrievalResult]:
        return self._search_channels(
            Question(qid="retrieval", question=" ".join(queries), answer_format="open", metadata=metadata or {}),
            queries,
            filter_doc_ids=filter_doc_ids,
            top_k_per_query=top_k_per_query,
            fused_top_k=fused_top_k,
            source=source,
        )

    def candidate_doc_filter(self, question: Question, *, restrict_to_doc_ids: bool) -> set[str] | None:
        if restrict_to_doc_ids and question.doc_ids:
            return set(question.doc_ids)
        if self.doc_index:
            doc_ids = self.doc_index.search_doc_ids(
                question_with_options(question),
                top_k=self.blind_top_docs,
                domain=question.domain or None,
            )
            return set(doc_ids) if doc_ids else None
        return None

    def _search_channels(
        self,
        question: Question,
        queries: list[str],
        *,
        filter_doc_ids: set[str] | None,
        top_k_per_query: int | None = None,
        fused_top_k: int | None = None,
        source: str,
    ) -> list[RetrievalResult]:
        # Extract kb_id or kb_ids from question metadata
        kb_id = question.metadata.get("kb_id") if question.metadata else None
        kb_ids = question.metadata.get("kb_ids") if question.metadata else None

        context = SearchContext(
            question=question,
            queries=[query for query in queries if query],
            filter_doc_ids=filter_doc_ids,
            metadata={
                "top_k_per_query": top_k_per_query or self.top_k_per_query,
                "fused_top_k": fused_top_k or self.fused_top_k,
                "scoring_mode": self.scoring_mode,
                "source": source,
                "kb_id": kb_id,
                "kb_ids": kb_ids,
            },
        )
        channel_results = [channel.search(context) for channel in self.channels if channel.enabled(context)]
        ranked_lists = [result.results for result in channel_results if result.results]
        if not ranked_lists:
            return []
        if len(ranked_lists) == 1:
            fused = ranked_lists[0][: fused_top_k or self.fused_top_k]
        else:
            weights = [self.channel_weights.get(result.channel, 1.0) for result in channel_results if result.results]
            fused = reciprocal_rank_fusion(ranked_lists, top_k=fused_top_k or self.fused_top_k, weights=weights)

        # Filter by kb_id (single KB) or kb_ids (multiple KBs)
        if kb_ids:
            # 多知识库融合模式：只保留属于任一选中 KB 的结果
            kb_ids_set = set(kb_ids)
            fused = [r for r in fused if r.metadata.get("kb_id") in kb_ids_set]
        elif kb_id:
            # 单知识库隔离模式：只保留属于该 KB 的结果
            fused = [r for r in fused if r.metadata.get("kb_id") == kb_id]

        return fused
