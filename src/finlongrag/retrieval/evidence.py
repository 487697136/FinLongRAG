"""Evidence selection and compression."""

from __future__ import annotations

import re

from finlongrag.core.schema import Claim, RetrievalResult


def select_evidence(
    claim: Claim,
    candidates: list[RetrievalResult],
    *,
    top_k: int,
    max_chars: int,
) -> list[RetrievalResult]:
    scored = sorted(candidates, key=lambda item: _score(claim, item), reverse=True)
    selected: list[RetrievalResult] = []
    seen: set[str] = set()
    used_chars = 0

    if claim.claim_type == "comparison":
        for doc_id in claim.doc_scope:
            item = next((candidate for candidate in scored if candidate.doc_id == doc_id), None)
            if item is not None:
                used_chars = _try_add(item, selected, seen, used_chars, max_chars)
            if len(selected) >= top_k:
                return selected

    for item in scored:
        if len(selected) >= top_k:
            break
        used_chars = _try_add(item, selected, seen, used_chars, max_chars)
    return selected


def format_evidence(evidence: list[RetrievalResult]) -> str:
    blocks = []
    for index, item in enumerate(evidence, start=1):
        blocks.append(
            f"[E{index}] doc={item.doc_id} page={item.metadata.get('page')} "
            f"section={item.metadata.get('section', '')}\n{item.evidence_text.strip()}"
        )
    return "\n\n".join(blocks) if blocks else "未检索到证据。"


def _score(claim: Claim, item: RetrievalResult) -> float:
    text = item.evidence_text or ""
    compact = re.sub(r"\s+", "", text)
    score = float(item.score)
    score += 1.2 * sum(1 for term in claim.must_terms[:8] if term and re.sub(r"\s+", "", term) in compact)
    score += 0.5 * sum(1 for term in claim.should_terms[:8] if term and re.sub(r"\s+", "", term) in compact)
    score += 0.8 * sum(1 for value in claim.numbers[:5] if value and value in text)
    score += 0.8 * sum(1 for value in claim.dates[:5] if value and value in text)
    if item.metadata.get("chunk_type") == "table_row" and claim.claim_type in {"metric_fact", "comparison"}:
        score += 1.2
    if item.metadata.get("clause_id") and claim.claim_type == "clause_consequence":
        score += 0.8
    if len(text) > 900:
        score -= min(1.0, (len(text) - 900) / 1000)
    return score


def _try_add(
    item: RetrievalResult,
    selected: list[RetrievalResult],
    seen: set[str],
    used_chars: int,
    max_chars: int,
) -> int:
    if item.chunk_id in seen:
        return used_chars
    text = item.evidence_text.strip()
    if not text:
        return used_chars
    if selected and used_chars + len(text) > max_chars:
        return used_chars
    selected.append(item)
    seen.add(item.chunk_id)
    return used_chars + len(text)

