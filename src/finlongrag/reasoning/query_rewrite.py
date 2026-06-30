"""Query rewriting and sub-query generation.

Uses optional LLM entity extraction to build targeted sub-queries. Falls back to
rule-based term extraction when no LLM is available.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from finlongrag.core.schema import Question
from finlongrag.ingestion.chunker import extract_dates, extract_numbers
from finlongrag.retrieval.queries import RELATION_TERMS, extract_entities, question_with_options

if TYPE_CHECKING:
    from finlongrag.reasoning.llm import ChatModel


_ENTITY_SYSTEM_PROMPT = (
    "你是问题实体提取器。从问题文本中提取有助于文档检索的关键实体，以 JSON 返回，"
    "缺失字段用 null 或空列表。\n"
    "JSON 结构：\n"
    "{\n"
    '  "topics": ["主题/概念"],\n'
    '  "entities": ["人名、机构、产品等专有名词"],\n'
    '  "time_refs": ["时间/期间，如2023年、Q3"],\n'
    '  "metrics": ["指标或数值相关词"],\n'
    '  "doc_scope": ["文档类型或范围提示"]\n'
    "}\n"
    "只输出 JSON，不要 Markdown 代码块。"
)


@dataclass(frozen=True)
class QueryEntities:
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    time_refs: list[str] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    doc_scope: list[str] = field(default_factory=list)
    inherited_fields: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topics": list(self.topics),
            "entities": list(self.entities),
            "time_refs": list(self.time_refs),
            "metrics": list(self.metrics),
            "doc_scope": list(self.doc_scope),
            "inherited_fields": list(self.inherited_fields),
        }

    def all_terms(self) -> list[str]:
        return [
            term
            for group in (self.topics, self.entities, self.time_refs, self.metrics, self.doc_scope)
            for term in group
            if term
        ]


@dataclass(frozen=True)
class QueryRewriteResult:
    original: str
    rewritten: str
    sub_queries: list[str]
    entities: list[str]
    numbers: list[str]
    dates: list[str]
    query_entities: QueryEntities = field(default_factory=QueryEntities)

    def to_dict(self) -> dict:
        return {
            "original": self.original,
            "rewritten": self.rewritten,
            "sub_queries": list(self.sub_queries),
            "entities": list(self.entities),
            "numbers": list(self.numbers),
            "dates": list(self.dates),
            "query_entities": self.query_entities.to_dict(),
        }


class EntityExtractor:
    """LLM-powered entity extractor with multi-turn inheritance."""

    def __init__(self, llm: ChatModel) -> None:
        self._llm = llm

    def extract(
        self,
        question_text: str,
        *,
        history_entities: dict[str, Any] | None = None,
    ) -> QueryEntities:
        raw = self._call_llm(question_text)
        inherited_fields: list[str] = []
        if history_entities:
            raw, inherited_fields = self._inherit_missing(raw, history_entities)
        return QueryEntities(
            topics=_as_list(raw.get("topics")),
            entities=_as_list(raw.get("entities")),
            time_refs=_as_list(raw.get("time_refs")),
            metrics=_as_list(raw.get("metrics")),
            doc_scope=_as_list(raw.get("doc_scope")),
            inherited_fields=inherited_fields,
        )

    def _call_llm(self, question_text: str) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": _ENTITY_SYSTEM_PROMPT},
            {"role": "user", "content": f"问题：{question_text[:600]}"},
        ]
        try:
            response = self._llm.chat(messages, temperature=0.0, max_tokens=256)
            text = re.sub(r"```(?:json)?\s*", "", (response.text or "").strip()).strip("`").strip()
            return json.loads(text)
        except Exception:
            return {}

    @staticmethod
    def _inherit_missing(raw: dict[str, Any], history: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        inherited: list[str] = []
        for field_name in ("entities", "time_refs", "doc_scope", "topics"):
            if not _as_list(raw.get(field_name)) and history.get(field_name):
                raw[field_name] = history[field_name]
                inherited.append(field_name)
        return raw, inherited


class QueryRewriter:
    def __init__(self, llm: ChatModel | None = None) -> None:
        self._extractor = EntityExtractor(llm) if llm is not None else None

    def rewrite(
        self,
        question: Question,
        *,
        history: str = "",
        history_entities: dict[str, Any] | None = None,
    ) -> QueryRewriteResult:
        original = question_with_options(question) if question.options else question.question
        analysis_text = "\n".join(part for part in [history, original] if part)

        entities = extract_entities(analysis_text)
        numbers = extract_numbers(analysis_text)
        dates = extract_dates(analysis_text)
        relations = [term for term in RELATION_TERMS if term in analysis_text]

        query_entities = QueryEntities()
        if self._extractor is not None:
            try:
                query_entities = self._extractor.extract(original, history_entities=history_entities)
            except Exception:
                pass

        entity_terms = query_entities.all_terms()
        core_terms = list(dict.fromkeys([*entity_terms[:8], *entities[:4], *relations[:4], *dates[:2], *numbers[:2]]))
        rewritten = " ".join(core_terms) or original

        sub_queries = _dedupe(
            [
                original,
                rewritten,
                _focused_query(query_entities.entities, query_entities.metrics, query_entities.time_refs),
                _focused_query(query_entities.topics, query_entities.doc_scope, []),
                _history_focus_query(history, original),
                " ".join([*relations, *dates[:3], *numbers[:3]]),
                *[f"{entity} {' '.join(relations[:3])}" for entity in entities[:3]],
            ]
        )[:8]

        return QueryRewriteResult(
            original=original,
            rewritten=rewritten,
            sub_queries=sub_queries,
            entities=entities,
            numbers=numbers,
            dates=dates,
            query_entities=query_entities,
        )

    def refine(self, question: Question, *, gap: str, history: str = "") -> list[str]:
        original = question_with_options(question) if question.options else question.question
        refined = [original, f"{original} {gap}"]
        if self._extractor is not None:
            try:
                query_entities = self._extractor.extract(original)
                refined.extend(query_entities.all_terms()[:3])
            except Exception:
                pass
        return _dedupe(refined)[:4]


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = " ".join(str(item or "").split())
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if v]
    return [str(value).strip()] if str(value).strip() else []


def _focused_query(groups: list[str], targets: list[str], contexts: list[str]) -> str:
    parts = [*groups[:2], *targets[:2], *contexts[:2]]
    return " ".join(p for p in parts if p)


def _history_focus_query(history: str, question: str) -> str:
    if not history:
        return ""
    history_terms = [term for term in RELATION_TERMS if term in history]
    if not history_terms:
        return ""
    return " ".join([question, *history_terms[:4]])


# Backward-compatible aliases
FinancialEntities = QueryEntities
FinancialEntityExtractor = EntityExtractor
