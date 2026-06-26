"""Sparse BM25 / BM25F-lite index."""

from __future__ import annotations

import math
import pickle
from collections import Counter, defaultdict
from pathlib import Path

from finlongrag.core.schema import Chunk, RetrievalResult
from finlongrag.index.tokenizer import tokenize, tokenize_chunk_text


class SimpleBM25:
    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.corpus_tokens = corpus_tokens
        self.k1 = k1
        self.b = b
        self.doc_count = len(corpus_tokens)
        self.doc_lens = [len(tokens) for tokens in corpus_tokens]
        self.avgdl = sum(self.doc_lens) / max(1, self.doc_count)
        self.term_freqs = [Counter(tokens) for tokens in corpus_tokens]
        self.postings: dict[str, list[tuple[int, int]]] = {}
        doc_freq: Counter[str] = Counter()
        for doc_idx, freqs in enumerate(self.term_freqs):
            for term, tf in freqs.items():
                self.postings.setdefault(term, []).append((doc_idx, tf))
            doc_freq.update(freqs.keys())
        self.idf = {
            term: math.log(1 + (self.doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in doc_freq.items()
        }

    def get_score_items(self, query_tokens: list[str]) -> list[tuple[int, float]]:
        scores: dict[int, float] = {}
        for token in set(query_tokens):
            idf = self.idf.get(token, 0.0)
            if idf <= 0:
                continue
            for doc_idx, tf in self.postings.get(token, []):
                doc_len = self.doc_lens[doc_idx] or 1
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / max(1e-9, self.avgdl))
                scores[doc_idx] = scores.get(doc_idx, 0.0) + idf * (tf * (self.k1 + 1)) / denom
        return list(scores.items())


class BM25FIndex:
    FIELD_WEIGHTS = {
        "base": 1.0,
        "title": 0.25,
        "section": 0.25,
        "clause": 0.35,
        "numbers": 0.40,
        "dates": 0.35,
        "structured": 0.55,
    }

    def __init__(self, chunks: list[Chunk], tokenizer_mode: str = "mixed") -> None:
        self.chunks = list(chunks)
        self.tokenizer_mode = tokenizer_mode
        self.chunk_by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self.doc_chunks: dict[str, list[Chunk]] = defaultdict(list)
        for chunk in self.chunks:
            self.doc_chunks[chunk.doc_id].append(chunk)

        self.base_tokens = [
            tokenize_chunk_text(chunk.text, chunk.metadata.get("extra_index_fields", []), mode=tokenizer_mode)
            for chunk in self.chunks
        ]
        self.base_engine = SimpleBM25(self.base_tokens)
        self.field_engines = self._build_field_engines()

    @classmethod
    def build(cls, chunks: list[Chunk], tokenizer_mode: str = "mixed") -> BM25FIndex:
        return cls(chunks, tokenizer_mode=tokenizer_mode)

    def search(
        self,
        query: str,
        top_k: int = 20,
        filter_doc_ids: set[str] | None = None,
        source: str = "bm25f",
        scoring_mode: str = "bm25f",
    ) -> list[RetrievalResult]:
        query_tokens = tokenize(query, mode=self.tokenizer_mode)
        if not query_tokens:
            return []
        scores = self._bm25f_scores(query_tokens) if scoring_mode == "bm25f" else self._base_scores(query_tokens)
        ranked = sorted(scores.items(), key=lambda row: row[1], reverse=True)
        output: list[RetrievalResult] = []
        for idx, score in ranked:
            if score <= 0:
                continue
            chunk = self.chunks[idx]
            if filter_doc_ids and chunk.doc_id not in filter_doc_ids:
                continue
            output.append(self.result_from_chunk(chunk, float(score), source, query))
            if len(output) >= top_k:
                break
        return output

    def result_from_chunk(self, chunk: Chunk, score: float, source: str, query: str) -> RetrievalResult:
        return RetrievalResult(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            domain=chunk.domain,
            evidence_text=chunk.text,
            score=float(score),
            source=source,
            query=query,
            metadata={
                "page": chunk.page,
                "section": chunk.section,
                "clause_id": chunk.clause_id,
                "numbers": list(chunk.numbers),
                "dates": list(chunk.dates),
                "title": chunk.metadata.get("title", ""),
                "chunk_type": chunk.metadata.get("chunk_type", "atomic_text"),
                "extra_index_fields": chunk.metadata.get("extra_index_fields", []),
                "path": chunk.metadata.get("path", ""),
            },
        )

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        return self.chunk_by_id.get(chunk_id)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"chunks": self.chunks, "tokenizer_mode": self.tokenizer_mode}, f)

    @classmethod
    def load(cls, path: Path) -> BM25FIndex:
        with path.open("rb") as f:
            payload = pickle.load(f)
        return cls(payload["chunks"], tokenizer_mode=payload.get("tokenizer_mode", "mixed"))

    def _base_scores(self, query_tokens: list[str]) -> dict[int, float]:
        return {idx: score for idx, score in self.base_engine.get_score_items(query_tokens)}

    def _bm25f_scores(self, query_tokens: list[str]) -> dict[int, float]:
        components: dict[int, dict[str, float]] = defaultdict(dict)
        for idx, score in self.base_engine.get_score_items(query_tokens):
            components[idx]["base"] = score
        for field, engine in self.field_engines.items():
            for idx, score in engine.get_score_items(query_tokens):
                components[idx][field] = score
        maxima = {
            field: max((parts.get(field, 0.0) for parts in components.values()), default=0.0)
            for field in self.FIELD_WEIGHTS
        }
        output: dict[int, float] = {}
        for idx, parts in components.items():
            total = 0.0
            for field, weight in self.FIELD_WEIGHTS.items():
                max_score = maxima[field]
                normalized = parts.get(field, 0.0) / max_score if max_score > 0 else 0.0
                total += normalized * weight
            output[idx] = total
        return output

    def _build_field_engines(self) -> dict[str, SimpleBM25]:
        corpora = {field: [] for field in self.FIELD_WEIGHTS if field != "base"}
        for chunk in self.chunks:
            corpora["title"].append(tokenize(str(chunk.metadata.get("title", "")), mode=self.tokenizer_mode))
            corpora["section"].append(tokenize(chunk.section, mode=self.tokenizer_mode))
            corpora["clause"].append(tokenize(chunk.clause_id, mode=self.tokenizer_mode))
            corpora["numbers"].append(tokenize(" ".join(chunk.numbers), mode=self.tokenizer_mode))
            corpora["dates"].append(tokenize(" ".join(chunk.dates), mode=self.tokenizer_mode))
            corpora["structured"].append(
                tokenize(" ".join(str(x) for x in chunk.metadata.get("extra_index_fields", [])), mode=self.tokenizer_mode)
            )
        return {field: SimpleBM25(tokens) for field, tokens in corpora.items()}

