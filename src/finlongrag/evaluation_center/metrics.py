"""Evaluation metrics."""

from __future__ import annotations

from finlongrag.evaluation_center.schemas import EvalItemResult, EvalMetrics


def compute_metrics(details: list[EvalItemResult]) -> EvalMetrics:
    total = len(details)
    if total == 0:
        return EvalMetrics()
    hit_count = sum(1 for item in details if item.hit)
    reciprocal_ranks = [1.0 / item.rank if item.hit and item.rank > 0 else 0.0 for item in details]
    return EvalMetrics(
        total=total,
        hit_count=hit_count,
        recall=round(hit_count / total, 4),
        mrr=round(sum(reciprocal_ranks) / total, 4),
    )

