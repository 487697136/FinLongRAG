"""Deterministic tool fusion for numeric financial questions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finlongrag.core.schema import Question, RetrievalResult
from finlongrag.reasoning.calc_chain import CalcChain
from finlongrag.reasoning.fact_ledger import compile_numeric_fact_ledger, format_fact_ledger


@dataclass(frozen=True)
class ToolRunReport:
    use_calculator: bool
    fact_count: int
    calc_operations: int
    context_block: str
    ledger: dict[str, Any] = field(default_factory=dict)
    calc: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_calculator": self.use_calculator,
            "fact_count": self.fact_count,
            "calc_operations": self.calc_operations,
            "has_context": bool(self.context_block.strip()),
            "ledger": self.ledger,
            "calc": self.calc,
        }


class NumericToolRunner:
    """Compile fact ledger + deterministic calc chain from retrieved evidence."""

    def run(self, question: Question, evidence: list[RetrievalResult], *, enabled: bool = True) -> ToolRunReport:
        if not enabled or not evidence:
            return ToolRunReport(use_calculator=False, fact_count=0, calc_operations=0, context_block="")

        ledger = compile_numeric_fact_ledger(question, evidence)
        calc_result = CalcChain().run_from_fact_ledger(ledger, question.question)
        parts: list[str] = []
        if ledger.get("fact_count"):
            parts.append("[数值事实账本]\n" + format_fact_ledger(ledger))
        if calc_result.formatted_block:
            parts.append(calc_result.formatted_block)
        return ToolRunReport(
            use_calculator=True,
            fact_count=int(ledger.get("fact_count") or 0),
            calc_operations=len(calc_result.operations),
            context_block="\n\n".join(parts),
            ledger=ledger,
            calc=calc_result.to_dict(),
        )
