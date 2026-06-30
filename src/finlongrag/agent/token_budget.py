"""Evidence token/char budget allocation for RAG runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finlongrag.core.config import Settings


@dataclass(frozen=True)
class EvidenceBudget:
    max_evidence_chars: int
    evidence_top_k: int
    rerank_top_k: int

    def to_dict(self) -> dict[str, int]:
        return {
            "max_evidence_chars": self.max_evidence_chars,
            "evidence_top_k": self.evidence_top_k,
            "rerank_top_k": self.rerank_top_k,
        }


def allocate_evidence_budget(
    settings: Settings,
    *,
    intent: dict[str, Any] | None = None,
    history_chars: int = 0,
) -> EvidenceBudget:
    """Allocate per-request evidence budget (engineering guardrail, not competition scoring)."""
    max_chars = settings.max_evidence_chars
    evidence_top_k = settings.evidence_top_k
    rerank_top_k = max(evidence_top_k * settings.rerank_top_k_multiplier, evidence_top_k)

    if intent and intent.get("dense_evidence"):
        max_chars = int(max_chars * 1.15)
        evidence_top_k = min(evidence_top_k + 2, 16)

    # Long conversation history consumes prompt budget — trim evidence slightly.
    if history_chars > 1200:
        ratio = min(0.85, max(0.65, 1.0 - (history_chars - 1200) / 8000))
        max_chars = max(4000, int(max_chars * ratio))

    return EvidenceBudget(
        max_evidence_chars=max_chars,
        evidence_top_k=evidence_top_k,
        rerank_top_k=rerank_top_k,
    )
