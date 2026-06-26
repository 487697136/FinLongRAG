"""Agent plan construction.

The plan is not a free-form LLM plan. It is a deterministic execution contract
that can be shown in traces, tests, and later API responses.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from finlongrag.agent.router import RouteDecision, RouteType
from finlongrag.core.schema import Question


@dataclass(frozen=True)
class AgentStep:
    step_id: str
    action: str
    purpose: str
    depends_on: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AgentPlan:
    route: str
    steps: list[AgentStep]

    def to_dict(self) -> dict:
        return {"route": self.route, "steps": [step.to_dict() for step in self.steps]}


class AgentPlanner:
    def build(self, question: Question, route: RouteDecision) -> AgentPlan:
        if route.route == RouteType.CLAIM_VERIFICATION:
            return AgentPlan(
                route=route.route.value,
                steps=[
                    AgentStep("analyze", "decompose_claims", "split the question into independently verifiable claims"),
                    AgentStep("retrieve", "retrieve_claim_evidence", "retrieve evidence per claim", ["analyze"]),
                    AgentStep("verify", "verify_claims", "judge each claim with cited evidence", ["retrieve"]),
                    AgentStep("assemble", "assemble_answer", "compose final answer from claim verdicts", ["verify"]),
                    AgentStep("audit", "self_check", "record evidence quality and residual risk", ["assemble"]),
                ],
            )
        if route.route == RouteType.DOCUMENT_COMPARE:
            return AgentPlan(
                route=route.route.value,
                steps=[
                    AgentStep("rewrite", "build_comparison_queries", "extract comparison endpoints and metrics"),
                    AgentStep("retrieve", "retrieve_balanced_evidence", "keep coverage across documents", ["rewrite"]),
                    AgentStep("ledger", "compile_fact_ledger", "extract comparable numeric or factual anchors", ["retrieve"]),
                    AgentStep("answer", "grounded_answer", "answer with evidence and ledger support", ["ledger"]),
                ],
            )
        if route.route == RouteType.NUMERIC_QA:
            return AgentPlan(
                route=route.route.value,
                steps=[
                    AgentStep("rewrite", "build_numeric_queries", "extract metrics, dates, units, and entities"),
                    AgentStep("retrieve", "retrieve_numeric_evidence", "retrieve value-bearing evidence", ["rewrite"]),
                    AgentStep("ledger", "compile_fact_ledger", "normalize numbers and units", ["retrieve"]),
                    AgentStep("answer", "grounded_answer", "answer with cited calculation context", ["ledger"]),
                ],
            )
        return AgentPlan(
            route=route.route.value,
            steps=[
                AgentStep("rewrite", "rewrite_open_query", "create deterministic subqueries"),
                AgentStep("retrieve", "retrieve_evidence", "retrieve grounded evidence", ["rewrite"]),
                AgentStep("grade", "grade_evidence", "check evidence coverage before generation", ["retrieve"]),
                AgentStep("answer", "grounded_answer", "produce cited answer", ["grade"]),
            ],
        )

