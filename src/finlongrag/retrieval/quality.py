"""Evidence quality assessment with gating and gap summary."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from finlongrag.core.schema import Question, RetrievalResult
from finlongrag.ingestion.chunker import extract_dates, extract_numbers
from finlongrag.retrieval.queries import extract_entities

# Flags that block answer generation and trigger a retry.
# Only "no_evidence" is a hard blocker; missing_doc_coverage is a soft signal
# that the LLM can still handle (it will note missing information in its answer).
_CRITICAL_FLAGS = frozenset({"no_evidence"})

# Coverage ratio below which we refuse after retry (only used for doc-scoped Qs)
_UNSATISFACTORY_THRESHOLD = 0.30


@dataclass(frozen=True)
class EvidenceQualityReport:
    evidence_count: int
    covered_doc_ids: list[str]
    missing_doc_ids: list[str]
    entity_hits: list[str]
    number_hits: list[str]
    date_hits: list[str]
    has_numeric_evidence: bool
    has_structured_evidence: bool
    coverage_ratio: float
    risk_flags: list[str]

    # ── Gating API ────────────────────────────────────────────────────────────

    def has_critical_flags(self) -> bool:
        """Return True when evidence is so poor a retry is warranted."""
        return bool(set(self.risk_flags) & _CRITICAL_FLAGS)

    def is_unsatisfactory(self) -> bool:
        """Return True only when no evidence was found at all.

        We intentionally do NOT gate on coverage_ratio for chat-mode questions
        because: (a) entity extraction from short questions is unreliable,
        (b) coverage_ratio penalizes phrasing differences unfairly, and
        (c) the LLM can judge relevance better than a regex count.
        When doc_ids ARE required, low coverage is signalled via risk_flags so
        the LLM can mention missing information rather than refusing outright.
        """
        return self.evidence_count == 0

    def gap_summary(self) -> str:
        """Human-readable description of what evidence is missing."""
        parts: list[str] = []
        if not self.evidence_count:
            parts.append("没有检索到任何证据")
        if self.missing_doc_ids:
            parts.append(f"缺少文档: {', '.join(self.missing_doc_ids[:3])}")
        if "missing_question_numbers" in self.risk_flags:
            parts.append("证据中未找到问题相关数值")
        if "missing_question_dates" in self.risk_flags:
            parts.append("证据中未找到问题相关日期")
        if "low_coverage" in self.risk_flags:
            parts.append(f"覆盖率过低 ({self.coverage_ratio:.0%})")
        return "；".join(parts) if parts else "证据质量可接受"

    def to_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "has_critical_flags": self.has_critical_flags(),
            "is_unsatisfactory": self.is_unsatisfactory(),
            "gap_summary": self.gap_summary(),
        }


def assess_evidence_quality(question: Question, evidence: list[RetrievalResult]) -> EvidenceQualityReport:
    text = "\n".join(item.evidence_text for item in evidence)
    covered_doc_ids = list(dict.fromkeys(item.doc_id for item in evidence))
    missing_doc_ids = [doc_id for doc_id in question.doc_ids if doc_id not in covered_doc_ids]
    query_text = f"{question.question} {' '.join(question.options.values())}"
    entities = extract_entities(query_text)[:12]
    numbers = extract_numbers(query_text)[:8]
    dates = extract_dates(query_text)[:8]
    entity_hits = [item for item in entities if item in text]
    number_hits = [item for item in numbers if item in text]
    date_hits = [item for item in dates if item in text]
    has_numeric_evidence = any(item.metadata.get("numbers") for item in evidence)
    has_structured_evidence = any(item.metadata.get("chunk_type") == "table_row" for item in evidence)

    # Coverage is only meaningful when there are explicit doc_id requirements.
    # For open/chat questions (no doc_ids) we set coverage = 1.0 when evidence
    # exists, and 0.0 only when there is no evidence at all — avoiding false
    # refusals caused by entity-match failures on short conversational queries.
    required_doc_slots = len(set(question.doc_ids))
    covered_doc_slots = len(set(covered_doc_ids) & set(question.doc_ids))
    if required_doc_slots > 0:
        # Structured evaluation mode: weight doc coverage heavily, supplement with entity/number/date hits
        required_slots = required_doc_slots + len(numbers[:4]) + len(dates[:4])
        covered_slots = covered_doc_slots + len(number_hits[:4]) + len(date_hits[:4])
        coverage_ratio = min(1.0, covered_slots / required_slots) if required_slots > 0 else 1.0
    else:
        # Chat/open mode: if evidence was found, consider coverage satisfied
        coverage_ratio = 1.0 if evidence else 0.0

    risk_flags: list[str] = []
    if not evidence:
        risk_flags.append("no_evidence")
    if missing_doc_ids:
        risk_flags.append("missing_doc_coverage")
    if numbers and not number_hits:
        risk_flags.append("missing_question_numbers")
    if dates and not date_hits:
        risk_flags.append("missing_question_dates")
    if required_doc_slots > 0 and coverage_ratio < 0.35:
        risk_flags.append("low_coverage")
    return EvidenceQualityReport(
        evidence_count=len(evidence),
        covered_doc_ids=covered_doc_ids,
        missing_doc_ids=missing_doc_ids,
        entity_hits=entity_hits,
        number_hits=number_hits,
        date_hits=date_hits,
        has_numeric_evidence=has_numeric_evidence,
        has_structured_evidence=has_structured_evidence,
        coverage_ratio=coverage_ratio,
        risk_flags=risk_flags,
    )


def coverage_quota_select(
    results: list[RetrievalResult],
    *,
    top_k: int,
    doc_ids: list[str] | None = None,
) -> list[RetrievalResult]:
    """Select top_k results ensuring per-document coverage quota.

    For multi-doc compare routes, guarantees each compared document
    contributes at least ceil(top_k / doc_count) chunks before filling
    with the overall top scorers.

    Args:
        results: Full candidate list, sorted by score descending.
        top_k: Maximum evidence items to return.
        doc_ids: Required document IDs that must have representation.
                 Defaults to all unique doc_ids in results.
    """
    if not results:
        return []

    if doc_ids is None:
        doc_ids = list(dict.fromkeys(r.doc_id for r in results))

    if len(doc_ids) <= 1:
        return results[:top_k]

    quota = max(1, -(-top_k // len(doc_ids)))  # ceiling division
    selected: list[RetrievalResult] = []
    per_doc: dict[str, list[RetrievalResult]] = {d: [] for d in doc_ids}
    remaining: list[RetrievalResult] = []

    for item in results:
        bucket = per_doc.get(item.doc_id)
        if bucket is not None and len(bucket) < quota:
            bucket.append(item)
        else:
            remaining.append(item)

    # Fill quota slots first
    for bucket in per_doc.values():
        selected.extend(bucket)

    # Top-up with best remaining candidates
    selected_ids = {r.chunk_id for r in selected}
    for item in remaining:
        if len(selected) >= top_k:
            break
        if item.chunk_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item.chunk_id)

    return selected[:top_k]
