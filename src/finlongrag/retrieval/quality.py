"""Evidence quality assessment."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from finlongrag.core.schema import Question, RetrievalResult
from finlongrag.ingestion.chunker import extract_dates, extract_numbers
from finlongrag.retrieval.queries import extract_entities


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

    def to_dict(self) -> dict:
        return asdict(self)


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
    required_slots = len(set(question.doc_ids)) + len(entities[:6]) + len(numbers[:4]) + len(dates[:4])
    covered_slots = len(set(covered_doc_ids) & set(question.doc_ids)) + len(entity_hits[:6]) + len(number_hits[:4]) + len(date_hits[:4])
    coverage_ratio = 1.0 if required_slots == 0 else min(1.0, covered_slots / required_slots)
    risk_flags: list[str] = []
    if not evidence:
        risk_flags.append("no_evidence")
    if missing_doc_ids:
        risk_flags.append("missing_doc_coverage")
    if numbers and not number_hits:
        risk_flags.append("missing_question_numbers")
    if dates and not date_hits:
        risk_flags.append("missing_question_dates")
    if coverage_ratio < 0.35:
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

