"""Agent plan construction.

Each AgentStep.action must match a handler registered on StepExecutor in
reasoning/pipeline.py for routes executed by the executor.

Structured and conversational routes bypass StepExecutor; their plan steps
document the imperative path for trace readability only.
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

    def step_actions(self) -> list[str]:
        return [step.action for step in self.steps]


_RAG_STEPS = [
    AgentStep("rewrite", "rewrite_query", "expand the question into targeted sub-queries"),
    AgentStep("retrieve", "hybrid_retrieve", "hybrid BM25 + vector retrieval", ["rewrite"]),
    AgentStep("rerank", "rerank_evidence", "cross-encoder rerank on candidate pool", ["retrieve"]),
    AgentStep("select", "select_evidence", "select diverse, budgeted evidence", ["rerank"]),
    AgentStep("quality", "assess_evidence", "quality gate with one controlled retry", ["select"]),
    AgentStep("answer", "generate_answer", "grounded answer generation", ["quality"]),
    AgentStep("cite", "validate_citations", "validate and fix [En] citations", ["answer"]),
]

_STRUCTURED_STEPS = [
    AgentStep(
        "verify",
        "claim_verification",
        "decompose claims, retrieve per-claim evidence, verify, assemble, and validate citations",
    ),
]

_CONVERSATIONAL_STEPS = [
    AgentStep("answer", "conversational_llm", "direct LLM answer without retrieval"),
]


class AgentPlanner:
    def build(self, question: Question, route: RouteDecision) -> AgentPlan:  # noqa: ARG002
        if route.route == RouteType.CONVERSATIONAL:
            return AgentPlan(route.route.value, list(_CONVERSATIONAL_STEPS))
        if route.route == RouteType.STRUCTURED:
            return AgentPlan(route.route.value, list(_STRUCTURED_STEPS))
        return AgentPlan(route.route.value, list(_RAG_STEPS))
