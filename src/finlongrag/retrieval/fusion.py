"""Rank fusion utilities."""

from __future__ import annotations

from finlongrag.core.schema import RetrievalResult


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalResult]],
    top_k: int,
    k: int = 60,
    weights: list[float] | None = None,
) -> list[RetrievalResult]:
    scores: dict[str, float] = {}
    best: dict[str, RetrievalResult] = {}
    weights = weights or [1.0] * len(ranked_lists)
    for list_index, ranked in enumerate(ranked_lists):
        weight = weights[list_index] if list_index < len(weights) else 1.0
        for rank, item in enumerate(ranked, start=1):
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + weight / (k + rank)
            if item.chunk_id not in best or item.score > best[item.chunk_id].score:
                best[item.chunk_id] = item
    output: list[RetrievalResult] = []
    for chunk_id, score in sorted(scores.items(), key=lambda row: row[1], reverse=True)[:top_k]:
        item = RetrievalResult.from_dict(best[chunk_id].to_dict())
        item.score = float(score)
        item.source = f"rrf:{item.source}"
        output.append(item)
    return output

