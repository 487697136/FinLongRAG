"""Deterministic query rewriting and subquery generation."""

from __future__ import annotations

from dataclasses import dataclass

from finlongrag.core.schema import Question
from finlongrag.ingestion.chunker import extract_dates, extract_numbers
from finlongrag.retrieval.queries import RELATION_TERMS, extract_entities, question_with_options


@dataclass(frozen=True)
class QueryRewriteResult:
    original: str
    rewritten: str
    sub_queries: list[str]
    entities: list[str]
    numbers: list[str]
    dates: list[str]

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "rewritten": self.rewritten,
            "sub_queries": list(self.sub_queries),
            "entities": list(self.entities),
            "numbers": list(self.numbers),
            "dates": list(self.dates),
        }


class QueryRewriter:
    """Rule-based query builder for open QA and product usage."""

    def rewrite(self, question: Question, *, history: str = "") -> QueryRewriteResult:
        original = question_with_options(question) if question.options else question.question
        analysis_text = "\n".join(part for part in [history, original] if part)
        entities = extract_entities(analysis_text)
        numbers = extract_numbers(analysis_text)
        dates = extract_dates(analysis_text)
        relations = [term for term in RELATION_TERMS if term in analysis_text]
        core_terms = [*entities[:6], *relations[:6], *dates[:3], *numbers[:3]]
        rewritten = " ".join(dict.fromkeys(core_terms)) or original
        sub_queries = _dedupe(
            [
                original,
                rewritten,
                _history_focus_query(history, original),
                " ".join([*relations, *dates[:3], *numbers[:3]]),
                *[f"{entity} {' '.join(relations[:3])}" for entity in entities[:4]],
            ]
        )[:8]
        return QueryRewriteResult(
            original=original,
            rewritten=rewritten,
            sub_queries=sub_queries,
            entities=entities,
            numbers=numbers,
            dates=dates,
        )


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = " ".join(str(item or "").split())
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def _history_focus_query(history: str, question: str) -> str:
    if not history:
        return ""
    history_terms = [term for term in RELATION_TERMS if term in history]
    if not history_terms:
        return ""
    return " ".join([question, *history_terms[:4]])
