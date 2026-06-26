"""Deterministic numeric fact extraction from evidence."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from finlongrag.core.schema import Question, RetrievalResult

VALUE_RE = re.compile(
    r"(?P<paren>[(（])?\s*(?P<value>[-+]?\d[\d,，]*(?:\.\d+)?)\s*"
    r"(?(paren)[)）])\s*(?P<unit>%|％|元|千元|百万元|万元|亿元|万|亿|倍)?"
)
YEAR_RE = re.compile(r"(?:19|20)\d{2}")
METRIC_TERMS = (
    "营业收入",
    "净利润",
    "归属于上市公司股东的净利润",
    "经营活动产生的现金流量净额",
    "研发投入",
    "研发投入占营业收入比例",
    "现金分红",
    "票面利率",
    "发行规模",
    "市场规模",
    "保险金额",
    "保险金",
)
UNIT_MULTIPLIERS = {
    "元": Decimal("1"),
    "千元": Decimal("1000"),
    "百万元": Decimal("1000000"),
    "万元": Decimal("10000"),
    "万": Decimal("10000"),
    "亿元": Decimal("100000000"),
    "亿": Decimal("100000000"),
    "%": Decimal("0.01"),
    "％": Decimal("0.01"),
    "倍": Decimal("1"),
}


@dataclass(frozen=True)
class NumericFact:
    fact_id: str
    doc_id: str
    chunk_id: str
    metric: str
    year: str
    raw_value: str
    unit: str
    normalized_value: str
    context: str

    def to_dict(self) -> dict:
        return asdict(self)


def compile_numeric_fact_ledger(
    question: Question,
    evidence: list[RetrievalResult],
    *,
    max_facts: int = 40,
) -> dict:
    query_text = f"{question.question} {' '.join(question.options.values())}"
    facts: list[tuple[float, NumericFact]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for evidence_index, item in enumerate(evidence, start=1):
        text = " ".join((item.evidence_text or "").split())
        for mention_index, match in enumerate(VALUE_RE.finditer(text), start=1):
            raw = match.group("value")
            unit = match.group("unit") or ""
            if _is_plain_year(raw, unit):
                continue
            negative = bool(match.group("paren")) and not raw.startswith("-")
            normalized = _normalize(raw, unit, negative=negative)
            if normalized is None:
                continue
            context = _context_window(text, match.start(), match.end())
            metric = _nearest_metric(context, query_text)
            year = _nearest_year(context)
            key = (item.doc_id, item.chunk_id, metric, year, f"{normalized}:{unit}")
            if key in seen:
                continue
            seen.add(key)
            fact = NumericFact(
                fact_id=f"F{evidence_index}_{mention_index}",
                doc_id=item.doc_id,
                chunk_id=item.chunk_id,
                metric=metric,
                year=year,
                raw_value=("(" if negative else "") + raw + (")" if negative else ""),
                unit=unit or "未标明",
                normalized_value=_decimal_text(normalized),
                context=context,
            )
            facts.append((_relevance(fact, query_text, item), fact))
    ranked = [fact for _, fact in sorted(facts, key=lambda row: (-row[0], row[1].fact_id))[:max_facts]]
    return {
        "facts": [fact.to_dict() for fact in ranked],
        "fact_count": len(ranked),
        "source_doc_ids": list(dict.fromkeys(fact.doc_id for fact in ranked)),
    }


def format_fact_ledger(ledger: dict) -> str:
    facts = ledger.get("facts") or []
    if not facts:
        return "无可抽取数值事实"
    return "\n".join(
        f"{fact['fact_id']} | doc={fact['doc_id']} | metric={fact['metric']} | year={fact['year']} | "
        f"raw={fact['raw_value']} {fact['unit']} | normalized={fact['normalized_value']} | {fact['context']}"
        for fact in facts
    )


def _normalize(raw: str, unit: str, *, negative: bool) -> Decimal | None:
    try:
        value = Decimal(raw.replace(",", "").replace("，", ""))
    except (InvalidOperation, ValueError):
        return None
    if negative:
        value = -value
    return value * UNIT_MULTIPLIERS.get(unit, Decimal("1"))


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _is_plain_year(raw: str, unit: str) -> bool:
    return not unit and bool(re.fullmatch(r"(?:19|20)\d{2}", raw.replace(",", "")))


def _context_window(text: str, start: int, end: int, radius: int = 64) -> str:
    return text[max(0, start - radius) : min(len(text), end + radius)].strip()


def _nearest_metric(context: str, query_text: str) -> str:
    candidates = [metric for metric in METRIC_TERMS if metric in context]
    if candidates:
        return max(candidates, key=len)
    candidates = [metric for metric in METRIC_TERMS if metric in query_text]
    return max(candidates, key=len) if candidates else "未识别指标"


def _nearest_year(context: str) -> str:
    matches = YEAR_RE.findall(context)
    return matches[-1] if matches else ""


def _relevance(fact: NumericFact, query_text: str, item: RetrievalResult) -> float:
    score = 0.0
    if fact.metric != "未识别指标":
        score += 2.0
        if fact.metric in query_text:
            score += 2.0
    if fact.year and fact.year in query_text:
        score += 1.5
    if fact.unit != "未标明":
        score += 0.8
    if item.metadata.get("chunk_type") == "table_row":
        score += 0.8
    score += min(1.0, float(item.score) * 10)
    return score

