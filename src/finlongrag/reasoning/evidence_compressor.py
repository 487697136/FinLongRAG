"""Local evidence compression for long contexts."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from finlongrag.core.schema import Question, RetrievalResult
from finlongrag.retrieval.queries import extract_entities


@dataclass(frozen=True)
class CompressionReport:
    original_count: int
    compressed_count: int
    original_chars: int
    compressed_chars: int

    def to_dict(self) -> dict:
        return asdict(self)


class EvidenceCompressor:
    def compress(
        self,
        question: Question,
        evidence: list[RetrievalResult],
        *,
        max_total_chars: int,
        max_item_chars: int = 1600,
    ) -> tuple[list[RetrievalResult], CompressionReport]:
        original_chars = sum(len(item.evidence_text or "") for item in evidence)
        query_terms = _query_terms(question)
        compressed: list[RetrievalResult] = []
        used_chars = 0
        for item in evidence:
            text = _compress_text(item.evidence_text, query_terms=query_terms, max_chars=max_item_chars)
            if compressed and used_chars + len(text) > max_total_chars:
                break
            cloned = RetrievalResult(
                chunk_id=item.chunk_id,
                doc_id=item.doc_id,
                domain=item.domain,
                evidence_text=text,
                score=item.score,
                source=item.source,
                query=item.query,
                metadata={**item.metadata, "compressed": text != item.evidence_text},
            )
            compressed.append(cloned)
            used_chars += len(text)
        return compressed, CompressionReport(
            original_count=len(evidence),
            compressed_count=len(compressed),
            original_chars=original_chars,
            compressed_chars=sum(len(item.evidence_text or "") for item in compressed),
        )


def _query_terms(question: Question) -> set[str]:
    text = f"{question.question} {' '.join(question.options.values())}"
    terms = set(extract_entities(text))
    terms.update(re.findall(r"(?:19|20)\d{2}\s*年?", text))
    terms.update(re.findall(r"\d+(?:\.\d+)?\s*(?:%|％|亿元|万元|元|倍)?", text))
    return {term.strip() for term in terms if len(term.strip()) >= 2}


def _compress_text(text: str, *, query_terms: set[str], max_chars: int) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= max_chars:
        return normalized
    sentences = [part.strip() for part in re.split(r"(?<=[。！？；\n])", normalized) if part.strip()]
    if not sentences:
        return normalized[:max_chars]
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        score = sum(1.0 for term in query_terms if term and term in sentence)
        if re.search(r"\d+(?:\.\d+)?\s*(?:%|％|亿元|万元|元|倍)?", sentence):
            score += 1.2
        if any(word in sentence for word in ("应当", "不得", "除外", "但是", "增长", "下降", "高于", "低于")):
            score += 0.6
        scored.append((score, index, sentence))
    keep: set[int] = set()
    total = 0
    for _, index, sentence in sorted(scored, key=lambda row: (row[0], -row[1]), reverse=True):
        if total + len(sentence) > max_chars:
            continue
        keep.add(index)
        total += len(sentence)
        if total >= max_chars * 0.85:
            break
    if not keep:
        return normalized[:max_chars]
    return "\n".join(sentences[index] for index in sorted(keep))[:max_chars]
