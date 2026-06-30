"""Citation validation for LLM-generated answers.

CitationValidator parses [E{n}] references produced by the LLM and maps them
to actual RetrievalResult entries.  Invalid references (n out of range) are
flagged and replaced with [INVALID_REF:{n}] in a corrected answer copy.

Structured citation data is stored in AnswerResult.metadata["citations"] and
surfaced to the API/frontend via the normal evidence payload.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from finlongrag.core.schema import RetrievalResult


# Matches [E1], [E12], etc. (case-insensitive E)
_CITATION_RE = re.compile(r"\[E(\d+)\]", re.IGNORECASE)


@dataclass(frozen=True)
class StructuredCitation:
    ref: str           # e.g. "E1"
    evidence_index: int  # 1-based, matches [E{n}] in answer
    chunk_id: str
    doc_id: str
    page: int | None
    section: str
    score: float
    valid: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CitationReport:
    total_refs: int
    valid_refs: int
    invalid_refs: list[str]
    citations: list[StructuredCitation]
    corrected_answer: str  # answer with [INVALID_REF:n] substitutions

    @property
    def has_invalid(self) -> bool:
        return bool(self.invalid_refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_refs": self.total_refs,
            "valid_refs": self.valid_refs,
            "invalid_refs": self.invalid_refs,
            "citations": [c.to_dict() for c in self.citations],
            "has_invalid": self.has_invalid,
        }

    def structured_citations_for_api(self) -> list[dict[str, Any]]:
        """Return only valid citations in a compact API-friendly format."""
        return [c.to_dict() for c in self.citations if c.valid]


class CitationValidator:
    """Parse and validate [E{n}] citations in LLM-generated answer text."""

    def validate(
        self,
        answer_text: str,
        evidence: list[RetrievalResult],
    ) -> CitationReport:
        """Validate all [E{n}] references in answer_text against evidence list.

        Args:
            answer_text: Raw text returned by the LLM.
            evidence: Ordered list of RetrievalResult used in prompt (1-indexed).

        Returns:
            CitationReport with structured_citations and a corrected_answer.
        """
        raw_refs = _CITATION_RE.findall(answer_text)
        seen: set[int] = set()
        citations: list[StructuredCitation] = []
        invalid_refs: list[str] = []

        for n_str in raw_refs:
            n = int(n_str)
            if n in seen:
                continue
            seen.add(n)

            if 1 <= n <= len(evidence):
                item = evidence[n - 1]
                citations.append(StructuredCitation(
                    ref=f"E{n}",
                    evidence_index=n,
                    chunk_id=item.chunk_id,
                    doc_id=item.doc_id,
                    page=item.metadata.get("page"),
                    section=str(item.metadata.get("section", "")),
                    score=round(float(item.score), 4),
                    valid=True,
                ))
            else:
                invalid_refs.append(f"E{n}")
                citations.append(StructuredCitation(
                    ref=f"E{n}",
                    evidence_index=n,
                    chunk_id="",
                    doc_id="",
                    page=None,
                    section="",
                    score=0.0,
                    valid=False,
                ))

        # Build corrected answer: replace invalid refs
        corrected = answer_text
        for inv in invalid_refs:
            corrected = corrected.replace(f"[{inv}]", f"[INVALID_REF:{inv[1:]}]")

        return CitationReport(
            total_refs=len(seen),
            valid_refs=sum(1 for c in citations if c.valid),
            invalid_refs=invalid_refs,
            citations=citations,
            corrected_answer=corrected,
        )
