"""Deterministic numerical reasoning chain for financial Q&A.

CalcChain provides Python-native arithmetic operations for common financial
calculations (YoY growth, QoQ change, proportion, unit normalization) so that
the LLM does not need to perform arithmetic.  Results are injected into the
prompt as a <calculation_result> block; the LLM only explains the result.

Usage::
    chain = CalcChain()
    result = chain.run_from_fact_ledger(ledger, question_text)
    # result.formatted_block → "<calculation_result>...</calculation_result>"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from finlongrag.reasoning.fact_ledger import UNIT_MULTIPLIERS, NumericFact

# ── Keywords that hint at what kind of calculation is needed ─────────────────

_YOY_RE = re.compile(r"同比|年增长|年增幅|较去年|较上年")
_QOQ_RE = re.compile(r"环比|季增长|季增幅|较上季|较前季")
_PROPORTION_RE = re.compile(r"占比|比例|百分比|占[总全]")
_COMPARE_RE = re.compile(r"高于|低于|多于|少于|差[了多少]|超过")
_GROWTH_RE = re.compile(r"增长率|增幅|增速|降幅|降速|变动率|变化幅度")


@dataclass
class CalcOperation:
    operation: str
    operands: list[str]
    result_raw: str
    result_formatted: str
    fact_ids: list[str]
    unit: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "operands": self.operands,
            "result_raw": self.result_raw,
            "result_formatted": self.result_formatted,
            "fact_ids": self.fact_ids,
            "unit": self.unit,
            "error": self.error,
        }


@dataclass
class CalcResult:
    operations: list[CalcOperation] = field(default_factory=list)
    summary: str = ""

    @property
    def formatted_block(self) -> str:
        if not self.operations:
            return ""
        lines = ["<calculation_result>"]
        for op in self.operations:
            if op.error:
                lines.append(f"  [{op.operation}] 错误：{op.error}")
            else:
                lines.append(
                    f"  [{op.operation}] {' vs '.join(op.operands)} → {op.result_formatted}"
                    + (f" ({op.unit})" if op.unit else "")
                    + f"  (来源: {', '.join(op.fact_ids)})"
                )
        if self.summary:
            lines.append(f"  摘要：{self.summary}")
        lines.append("</calculation_result>")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "operations": [op.to_dict() for op in self.operations],
            "summary": self.summary,
        }


class CalcChain:
    """Deterministic financial calculation engine."""

    # ── Public arithmetic operations ──────────────────────────────────────────

    def yoy_growth(self, current: Decimal, prior: Decimal) -> Decimal:
        """(current - prior) / |prior|  — year-over-year growth rate."""
        if prior == 0:
            raise ZeroDivisionError("prior year value is zero")
        return (current - prior) / abs(prior)

    def qoq_change(self, current: Decimal, prior: Decimal) -> Decimal:
        """(current - prior) / |prior|  — quarter-over-quarter change."""
        if prior == 0:
            raise ZeroDivisionError("prior quarter value is zero")
        return (current - prior) / abs(prior)

    def proportion(self, part: Decimal, total: Decimal) -> Decimal:
        """part / total — proportion/ratio."""
        if total == 0:
            raise ZeroDivisionError("total is zero")
        return part / total

    def difference(self, a: Decimal, b: Decimal) -> Decimal:
        return a - b

    def normalize_unit(self, value: Decimal, unit: str) -> Decimal:
        """Normalize value to base unit (元 / %)."""
        multiplier = UNIT_MULTIPLIERS.get(unit, Decimal("1"))
        return value * multiplier

    # ── High-level entry point ────────────────────────────────────────────────

    def run_from_fact_ledger(self, ledger: dict[str, Any], question_text: str) -> CalcResult:
        """Detect calculation type from question and apply to ledger facts."""
        facts_raw = ledger.get("facts") or []
        if not facts_raw:
            return CalcResult(summary="无可计算事实")

        # Reconstruct NumericFact objects from ledger dicts
        facts = [_dict_to_numeric_fact(f) for f in facts_raw]

        operations: list[CalcOperation] = []

        if _YOY_RE.search(question_text):
            operations.extend(self._compute_yoy(facts, question_text))
        if _QOQ_RE.search(question_text):
            operations.extend(self._compute_qoq(facts, question_text))
        if _PROPORTION_RE.search(question_text):
            operations.extend(self._compute_proportions(facts, question_text))
        if _COMPARE_RE.search(question_text) and not operations:
            operations.extend(self._compute_differences(facts, question_text))
        if _GROWTH_RE.search(question_text) and not operations:
            operations.extend(self._compute_yoy(facts, question_text))

        if not operations:
            # Default: summarize normalized values present in ledger
            summary = "; ".join(
                f"{f.metric}({f.year})={f.raw_value}{f.unit}"
                for f in facts[:6]
                if f.metric != "未识别指标"
            )
            return CalcResult(summary=summary or "数值已提取，无特定计算")

        return CalcResult(operations=operations)

    # ── Per-operation helpers ─────────────────────────────────────────────────

    def _compute_yoy(self, facts: list[NumericFact], question_text: str) -> list[CalcOperation]:
        """Find pairs of same metric across consecutive years, compute YoY."""
        ops: list[CalcOperation] = []
        metric_year_map: dict[tuple[str, str], NumericFact] = {}
        for f in facts:
            if f.metric != "未识别指标" and f.year:
                key = (f.metric, f.year)
                if key not in metric_year_map:
                    metric_year_map[key] = f

        # Group by metric, sort years
        by_metric: dict[str, list[tuple[str, NumericFact]]] = {}
        for (metric, year), fact in metric_year_map.items():
            by_metric.setdefault(metric, []).append((year, fact))

        for metric, year_facts in by_metric.items():
            if len(year_facts) < 2:
                continue
            year_facts.sort(key=lambda t: t[0])
            for i in range(len(year_facts) - 1):
                y_prior, f_prior = year_facts[i]
                y_curr, f_curr = year_facts[i + 1]
                try:
                    v_curr = _to_decimal(f_curr)
                    v_prior = _to_decimal(f_prior)
                    rate = self.yoy_growth(v_curr, v_prior)
                    pct = f"{float(rate) * 100:+.2f}%"
                    ops.append(CalcOperation(
                        operation="同比增长率",
                        operands=[f"{metric}({y_curr})", f"{metric}({y_prior})"],
                        result_raw=str(rate),
                        result_formatted=pct,
                        fact_ids=[f_curr.fact_id, f_prior.fact_id],
                        unit="增长率",
                    ))
                except (ZeroDivisionError, InvalidOperation, ValueError) as exc:
                    ops.append(CalcOperation(
                        operation="同比增长率",
                        operands=[f"{metric}({y_curr})", f"{metric}({y_prior})"],
                        result_raw="",
                        result_formatted="",
                        fact_ids=[f_curr.fact_id, f_prior.fact_id],
                        error=str(exc),
                    ))
        return ops[:4]  # cap to avoid flooding prompt

    def _compute_qoq(self, facts: list[NumericFact], question_text: str) -> list[CalcOperation]:
        """Quarter-over-quarter: same metric, consecutive periods."""
        # Reuse YoY logic — period detection is by year string for now
        return self._compute_yoy(facts, question_text)

    def _compute_proportions(self, facts: list[NumericFact], question_text: str) -> list[CalcOperation]:
        """Compute part/total for facts where one is a percentage denominator."""
        ops: list[CalcOperation] = []
        for part_fact in facts:
            for total_fact in facts:
                if part_fact.fact_id == total_fact.fact_id:
                    continue
                if part_fact.metric == "未识别指标" or total_fact.metric == "未识别指标":
                    continue
                # Heuristic: total metric contains part metric or question mentions both
                if part_fact.metric not in question_text:
                    continue
                try:
                    v_part = _to_decimal(part_fact)
                    v_total = _to_decimal(total_fact)
                    if v_total <= 0:
                        continue
                    ratio = self.proportion(v_part, v_total)
                    pct = f"{float(ratio) * 100:.2f}%"
                    ops.append(CalcOperation(
                        operation="占比",
                        operands=[part_fact.metric, total_fact.metric],
                        result_raw=str(ratio),
                        result_formatted=pct,
                        fact_ids=[part_fact.fact_id, total_fact.fact_id],
                        unit="占比",
                    ))
                    if len(ops) >= 2:
                        return ops
                except Exception:
                    continue
        return ops

    def _compute_differences(self, facts: list[NumericFact], question_text: str) -> list[CalcOperation]:
        """Compute absolute differences between same-metric, different-year facts."""
        ops: list[CalcOperation] = []
        by_metric: dict[str, list[NumericFact]] = {}
        for f in facts:
            if f.metric != "未识别指标":
                by_metric.setdefault(f.metric, []).append(f)

        for metric, mfacts in by_metric.items():
            if len(mfacts) < 2:
                continue
            mfacts_sorted = sorted(mfacts, key=lambda f: f.year or "")
            a, b = mfacts_sorted[-1], mfacts_sorted[0]
            try:
                va, vb = _to_decimal(a), _to_decimal(b)
                diff = self.difference(va, vb)
                unit = a.unit if a.unit == b.unit else "元（已归一化）"
                ops.append(CalcOperation(
                    operation="差值",
                    operands=[f"{metric}({a.year})", f"{metric}({b.year})"],
                    result_raw=str(diff),
                    result_formatted=_format_decimal(diff),
                    fact_ids=[a.fact_id, b.fact_id],
                    unit=unit,
                ))
                if len(ops) >= 3:
                    break
            except Exception:
                continue
        return ops


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dict_to_numeric_fact(d: dict[str, Any]) -> NumericFact:
    return NumericFact(
        fact_id=str(d.get("fact_id", "")),
        doc_id=str(d.get("doc_id", "")),
        chunk_id=str(d.get("chunk_id", "")),
        metric=str(d.get("metric", "未识别指标")),
        year=str(d.get("year", "")),
        raw_value=str(d.get("raw_value", "0")),
        unit=str(d.get("unit", "")),
        normalized_value=str(d.get("normalized_value", "0")),
        context=str(d.get("context", "")),
    )


def _to_decimal(fact: NumericFact) -> Decimal:
    """Parse normalized_value from a NumericFact (already in base unit)."""
    raw = fact.normalized_value.replace(",", "").replace("，", "").strip()
    # Strip leading/trailing parentheses (negative marker)
    raw = raw.strip("()")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"cannot parse '{raw}' as Decimal") from exc


def _format_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
