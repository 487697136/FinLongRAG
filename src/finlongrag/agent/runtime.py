"""Agent runtime: intent, cache, budget, and observability prelude before RAG execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from finlongrag.agent.intent_resolver import IntentResolution, IntentResolver
from finlongrag.agent.query_cache import CacheLookup, QueryAnswerCache
from finlongrag.agent.token_budget import EvidenceBudget, allocate_evidence_budget
from finlongrag.core.config import Settings
from finlongrag.core.schema import AnswerResult, Question
from finlongrag.framework.trace import TraceRecorder


@dataclass
class AgentRunContext:
    question: Question
    mode: str
    intent: IntentResolution
    budget: EvidenceBudget
    cache_lookup: CacheLookup
    cached_result: AnswerResult | None = None
    pipeline_stages: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "intent": self.intent.to_dict(),
            "budget": self.budget.to_dict(),
            "cache": {
                "hit": self.cache_lookup.hit,
                "key": self.cache_lookup.key[:12],
                "age_seconds": round(self.cache_lookup.age_seconds, 2),
            },
            "warnings": list(self.warnings),
            "pipeline_stages": list(self.pipeline_stages),
        }


class AgentRuntime:
    """Product-oriented agent prelude (ragent-style stages without MCP complexity)."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        intent_resolver: IntentResolver | None = None,
        query_cache: QueryAnswerCache | None = None,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self.settings = settings or Settings.from_file()
        self.intent_resolver = intent_resolver or IntentResolver(self.settings)
        self.query_cache = query_cache or QueryAnswerCache(
            max_entries=self.settings.query_cache_max_entries,
            ttl_seconds=self.settings.query_cache_ttl_seconds,
        )
        self.trace_recorder = trace_recorder

    def prepare_rag_run(
        self,
        question: Question,
        *,
        mode: str = "auto",
        history: str = "",
    ) -> AgentRunContext:
        stages: list[dict[str, Any]] = []
        node = self._start_stage("intent_resolve")
        intent = self.intent_resolver.resolve(question)
        self._finish_stage(node, {"intent_count": len(intent.intents)})
        stages.append({"stage": "intent_resolve", "intent": intent.to_dict()})

        warnings: list[str] = []
        if self.settings.require_kb_scope_for_rag:
            meta = question.metadata or {}
            if not meta.get("kb_id") and not meta.get("kb_ids") and not question.doc_ids:
                warnings.append("kb_scope_missing")

        node = self._start_stage("budget_allocate")
        budget = allocate_evidence_budget(
            self.settings,
            intent=intent.to_dict(),
            history_chars=len(history or ""),
        )
        self._finish_stage(node, budget.to_dict())
        stages.append({"stage": "budget_allocate", "budget": budget.to_dict()})

        cached_result = None
        cache_lookup = CacheLookup(hit=False, key="")
        if self.settings.query_cache_enabled and mode not in {"llm_only"} and not (history or "").strip():
            node = self._start_stage("cache_lookup")
            cache_lookup, cached_result = self.query_cache.lookup(question, mode=mode, history=history)
            self._finish_stage(node, {"hit": cache_lookup.hit})
            stages.append({"stage": "cache_lookup", "hit": cache_lookup.hit})

        return AgentRunContext(
            question=question,
            mode=mode,
            intent=intent,
            budget=budget,
            cache_lookup=cache_lookup,
            cached_result=cached_result,
            pipeline_stages=stages,
            warnings=warnings,
        )

    def store_cache(self, question: Question, result: AnswerResult, *, mode: str = "auto", history: str = "") -> None:
        if self.settings.query_cache_enabled and not (history or "").strip():
            self.query_cache.store(question, result, mode=mode, history=history)

    def clear_cache(self) -> None:
        self.query_cache.clear()

    def _start_stage(self, name: str):
        if self.trace_recorder is None:
            return None
        return self.trace_recorder.start_node(name, "agent_stage")

    def _finish_stage(self, node, extra: dict[str, Any] | None = None) -> None:
        if node is None or self.trace_recorder is None:
            return
        if extra:
            node.extra_data.update(extra)
        self.trace_recorder.finish_node(node)
