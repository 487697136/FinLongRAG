"""Deterministic route selection for agent workflows."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from finlongrag.core.schema import Question


class RouteType(str, Enum):
    CLAIM_VERIFICATION = "claim_verification"
    NUMERIC_QA = "numeric_qa"
    DOCUMENT_COMPARE = "document_compare"
    OPEN_QA = "open_qa"


@dataclass(frozen=True)
class RouteDecision:
    route: RouteType
    reason: str
    confidence: float = 1.0

    def to_dict(self) -> dict:
        return {"route": self.route.value, "reason": self.reason, "confidence": self.confidence}


_NUMERIC_HINTS = re.compile(r"多少|占比|比例|同比|环比|增长|下降|增幅|降幅|合计|总额|万元|亿元|%|计算|高于|低于")
_COMPARE_HINTS = re.compile(r"比较|对比|区别|差异|分别|相比|哪个|哪一|高于|低于|优于")
_VERIFY_HINTS = re.compile(r"是否|对不对|正确|错误|判断|下列|说法|符合|不符合|成立")


class AgentRouter:
    """Rule-first router; deterministic routing keeps evaluation reproducible."""

    def decide(self, question: Question) -> RouteDecision:
        text = f"{question.question} {' '.join(question.options.values())}"
        if question.options and question.answer_format in {"mcq", "multi", "tf"}:
            return RouteDecision(RouteType.CLAIM_VERIFICATION, "structured options require claim verification")
        if _COMPARE_HINTS.search(text):
            return RouteDecision(RouteType.DOCUMENT_COMPARE, "comparison-style wording", 0.78)
        if _NUMERIC_HINTS.search(text):
            return RouteDecision(RouteType.NUMERIC_QA, "numeric wording", 0.76)
        if _VERIFY_HINTS.search(text):
            return RouteDecision(RouteType.CLAIM_VERIFICATION, "verification wording", 0.72)
        return RouteDecision(RouteType.OPEN_QA, "default grounded QA", 0.60)

