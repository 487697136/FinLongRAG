"""Step execution engine for Agentic RAG."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from finlongrag.agent.planner import AgentPlan, AgentStep

logger = logging.getLogger(__name__)

_CRITICAL_ACTIONS = frozenset({
    "hybrid_retrieve",
    "rerank_evidence",
    "select_evidence",
    "assess_evidence",
    "generate_answer",
})

HandlerFn = Callable[["StepContext"], "StepContext"]


@dataclass
class StepContext:
    """Shared mutable context threaded through all plan steps."""

    question_text: str
    route: str
    plan_steps: list[str]

    outputs: dict[str, Any] = field(default_factory=dict)
    step_traces: list[dict[str, Any]] = field(default_factory=list)

    sub_queries: list[str] = field(default_factory=list)
    query_entities: dict[str, Any] = field(default_factory=dict)
    retrieved: list[Any] = field(default_factory=list)
    reranked: list[Any] = field(default_factory=list)
    evidence: list[Any] = field(default_factory=list)
    quality_report: Any = None
    answer_text: str = ""
    citations: list[dict[str, Any]] = field(default_factory=list)
    gated: bool = False
    failed: bool = False
    failure_error: str = ""

    def record_step(self, step_id: str, action: str, duration_ms: float, data: dict) -> None:
        self.step_traces.append({
            "step_id": step_id,
            "action": action,
            "duration_ms": round(duration_ms, 1),
            **data,
        })

    def to_trace(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "plan_steps": self.plan_steps,
            "step_traces": self.step_traces,
            "query_entities": self.query_entities,
            "sub_queries": self.sub_queries,
            "quality_flags": getattr(self.quality_report, "risk_flags", []),
            "citations_count": len(self.citations),
            "gated": self.gated,
        }


class StepExecutor:
    def __init__(self, *, trace_recorder: Any | None = None) -> None:
        self._handlers: dict[str, HandlerFn] = {}
        self._trace_recorder = trace_recorder

    def register(self, action: str, handler: HandlerFn) -> None:
        self._handlers[action] = handler

    def run(self, plan: AgentPlan, context: StepContext) -> StepContext:
        for step in plan.steps:
            context = self._execute_step(step, context)
            if context.gated or context.failed:
                break
        return context

    def _execute_step(self, step: AgentStep, context: StepContext) -> StepContext:
        handler = self._handlers.get(step.action)
        t0 = time.monotonic()
        trace_node = None
        if self._trace_recorder is not None:
            trace_node = self._trace_recorder.start_node(step.action, "rag_step", {"step_id": step.step_id})
        if handler is None:
            elapsed = (time.monotonic() - t0) * 1000
            logger.warning("No handler registered for action %r (step %s)", step.action, step.step_id)
            context.record_step(step.step_id, step.action, elapsed, {"status": "skipped_no_handler"})
            if trace_node is not None:
                trace_node.extra_data["status"] = "skipped_no_handler"
                self._trace_recorder.finish_node(trace_node)
            return context
        try:
            context = handler(context)
            elapsed = (time.monotonic() - t0) * 1000
            context.record_step(step.step_id, step.action, elapsed, {"status": "ok"})
            if trace_node is not None:
                trace_node.extra_data["status"] = "ok"
                self._trace_recorder.finish_node(trace_node)
        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            context.record_step(step.step_id, step.action, elapsed, {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            })
            if trace_node is not None:
                self._trace_recorder.finish_node(trace_node, "ERROR", f"{type(exc).__name__}: {exc}")
            context.outputs[step.step_id] = {"error": str(exc)}
            if step.action in _CRITICAL_ACTIONS:
                context.failed = True
                context.failure_error = f"{type(exc).__name__}: {exc}"
        return context
