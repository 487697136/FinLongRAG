"""Agentic reasoning pipeline.

Unified RAG path: rewrite → hybrid retrieve → rerank → select → quality gate →
generate → cite. Structured questions use claim verification; conversational
questions skip retrieval.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

from finlongrag.agent.executor import StepContext, StepExecutor
from finlongrag.agent.runtime import AgentRuntime
from finlongrag.agent.tools import NumericToolRunner
from finlongrag.framework.trace import TraceRecorder
from finlongrag.agent.memory import WorkingMemory
from finlongrag.agent.planner import AgentPlan, AgentPlanner
from finlongrag.agent.router import AgentRouter, RouteType
from finlongrag.core.config import Settings
from finlongrag.core.schema import AnswerResult, Question, TokenUsage
from finlongrag.reasoning.analyzer import QuestionAnalyzer
from finlongrag.reasoning.assembler import AnswerAssembler
from finlongrag.reasoning.citation_validator import CitationValidator
from finlongrag.reasoning.evidence_compressor import EvidenceCompressor
from finlongrag.reasoning.llm import ChatModel
from finlongrag.reasoning.prompts import build_open_answer_messages
from finlongrag.reasoning.query_rewrite import QueryRewriter
from finlongrag.reasoning.streaming import AnswerStreamEvent
from finlongrag.reasoning.verifier import ClaimVerifier
from finlongrag.retrieval.evidence import select_evidence
from finlongrag.retrieval.quality import assess_evidence_quality, coverage_quota_select
from finlongrag.retrieval.rerank import DashScopeEvidenceReranker, create_evidence_reranker, should_rerank
from finlongrag.retrieval.retriever import Retriever

_REFUSAL_ANSWER = "根据现有文档无法确定该问题的答案，证据不足。"
_CONVERSATIONAL_SYSTEM = (
    "你是长文本智能问答助手，支持文档理解与知识检索。"
    "请简洁友好地回答问候或关于助手功能的询问，不需要引用文档。"
)


class ReasoningPipeline:
    def __init__(
        self,
        retriever: Retriever,
        llm: ChatModel,
        *,
        evidence_top_k: int = 8,
        max_evidence_chars: int = 12000,
        evidence_per_claim: int = 4,
        evidence_chars_per_claim: int = 3200,
        settings: Settings | None = None,
        evidence_reranker: DashScopeEvidenceReranker | None = None,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self.settings = settings or Settings.from_file()
        self.retriever = retriever
        self.llm = llm
        self.trace_recorder = trace_recorder
        self.agent_runtime = AgentRuntime(self.settings, trace_recorder=trace_recorder)
        self.numeric_tools = NumericToolRunner()
        self.router = AgentRouter(llm=llm)
        self.planner = AgentPlanner()
        self.analyzer = QuestionAnalyzer()
        self.assembler = AnswerAssembler()
        self.query_rewriter = QueryRewriter(llm=llm)
        self.evidence_reranker = evidence_reranker or create_evidence_reranker(self.settings)
        self.evidence_compressor = EvidenceCompressor()
        self.evidence_top_k = evidence_top_k
        self.max_evidence_chars = max_evidence_chars
        self.rerank_top_k_multiplier = max(1, self.settings.rerank_top_k_multiplier)
        self.citation_validator = CitationValidator()
        self.verifier = ClaimVerifier(
            retriever,
            llm,
            evidence_per_claim=evidence_per_claim,
            evidence_chars_per_claim=evidence_chars_per_claim,
        )

    def answer(
        self,
        question: Question,
        *,
        history: str = "",
        history_entities: dict[str, Any] | None = None,
        mode: str = "auto",
    ) -> AnswerResult:
        if mode == "llm_only":
            trace_base: dict[str, Any] = {"route": {"route": "llm_only"}, "plan": {}}
            return self._answer_llm_only(question, trace=trace_base)

        route = self.router.decide(question)
        plan = self.planner.build(question, route)
        trace_base = {"route": route.to_dict(), "plan": plan.to_dict(), "mode": mode}

        if route.route == RouteType.CONVERSATIONAL:
            return self._answer_conversational(question, route.to_dict(), plan.to_dict(), trace=trace_base)

        if route.route == RouteType.STRUCTURED and question.options:
            scope_warnings = self._kb_scope_warnings(question)
            if scope_warnings:
                return self._build_scope_warning_result(
                    question, route, plan, trace_base, scope_warnings
                )
            return self._answer_structured(question, route.to_dict(), plan.to_dict(), trace=trace_base)

        return self._answer_rag(
            question,
            route,
            plan,
            history=history,
            history_entities=history_entities or {},
            trace=trace_base,
            mode=mode,
        )

    def answer_stream(
        self,
        question: Question,
        *,
        history: str = "",
        history_entities: dict[str, Any] | None = None,
        mode: str = "auto",
    ) -> Iterator[AnswerStreamEvent]:
        """Stream the final LLM tokens; retrieval/verification runs before streaming."""
        if mode == "llm_only":
            yield from self._stream_simple_llm(
                question,
                system=(
                    "你是长文本智能问答助手。当前为「仅模型回答」模式，"
                    "请直接根据已有知识回答，不需要引用文档。"
                    "若问题需要具体文件中的数据，请说明需要上传相关文档。"
                ),
                temperature=0.3,
                strategy="llm_only",
                trace={"route": {"route": "llm_only"}, "plan": {}},
            )
            return

        route = self.router.decide(question)
        plan = self.planner.build(question, route)
        trace_base: dict[str, Any] = {"route": route.to_dict(), "plan": plan.to_dict(), "mode": mode}

        if route.route == RouteType.CONVERSATIONAL:
            yield from self._stream_simple_llm(
                question,
                system=_CONVERSATIONAL_SYSTEM,
                temperature=0.3,
                max_tokens=256,
                strategy="conversational",
                trace=trace_base,
                extra_metadata={"route": route.to_dict(), "plan": plan.to_dict()},
            )
            return

        if route.route == RouteType.STRUCTURED and question.options:
            scope_warnings = self._kb_scope_warnings(question)
            if scope_warnings:
                result = self._build_scope_warning_result(
                    question, route, plan, trace_base, scope_warnings
                )
                yield AnswerStreamEvent(content=result.answer, done=True, result=result)
                return
            yield AnswerStreamEvent(status="verifying")
            result = self._answer_structured(question, route.to_dict(), plan.to_dict(), trace=trace_base)
            yield AnswerStreamEvent(content=result.answer, done=True, result=result)
            return

        yield from self._stream_rag(
            question,
            route,
            plan,
            history=history,
            history_entities=history_entities or {},
            trace=trace_base,
            mode=mode,
        )

    def _stream_simple_llm(
        self,
        question: Question,
        *,
        system: str,
        temperature: float,
        strategy: str,
        trace: dict[str, Any],
        max_tokens: int | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": question.question},
        ]
        parts: list[str] = []
        for chunk in self.llm.chat_stream(messages, temperature=temperature, max_tokens=max_tokens):
            if chunk.content:
                parts.append(chunk.content)
                yield AnswerStreamEvent(content=chunk.content)

        answer = "".join(parts).strip()
        usage = TokenUsage(
            prompt_tokens=max(1, sum(len(m.get("content", "")) for m in messages) // 2),
            completion_tokens=max(1, len(answer) // 2),
        )
        metadata = {
            "strategy": strategy,
            "gated": False,
            "trace": trace,
            **(extra_metadata or {}),
        }
        if strategy == "llm_only":
            metadata["route"] = {"route": "llm_only"}
            metadata["plan"] = {}

        result = AnswerResult(
            qid=question.qid,
            answer=answer,
            domain=question.domain,
            answer_format="open",
            confidence=1.0,
            evidence=[],
            token_usage=usage,
            raw_response=answer,
            metadata=metadata,
        )
        yield AnswerStreamEvent(done=True, result=result)

    def _stream_rag(
        self,
        question: Question,
        route: Any,
        plan: AgentPlan,
        *,
        history: str,
        history_entities: dict[str, Any],
        trace: dict[str, Any],
        mode: str,
    ) -> Iterator[AnswerStreamEvent]:
        run_ctx = self.agent_runtime.prepare_rag_run(question, mode=mode, history=history)
        trace["agent_runtime"] = run_ctx.to_dict()
        if run_ctx.cached_result is not None:
            trace["cache_hit"] = True
            cached = run_ctx.cached_result
            metadata = dict(cached.metadata or {})
            metadata["trace"] = {**(metadata.get("trace") or {}), **trace}
            yield AnswerStreamEvent(
                content=cached.answer,
                done=True,
                result=replace(cached, metadata=metadata),
            )
            return
        if self.settings.require_kb_scope_for_rag and run_ctx.warnings:
            result = self._build_scope_warning_result(question, route, plan, trace, run_ctx.warnings)
            yield AnswerStreamEvent(content=result.answer, done=True, result=result)
            return

        yield AnswerStreamEvent(status="retrieving")

        ctx, route, plan, trace = self._prepare_rag_context(
            question,
            route,
            plan,
            history=history,
            history_entities=history_entities,
            trace=trace,
            mode=mode,
            run_ctx=run_ctx,
        )
        prep_plan = AgentPlan(
            plan.route,
            [step for step in plan.steps if step.action not in {"generate_answer", "validate_citations"}],
        )
        executor = self._build_executor(question, run_ctx=run_ctx)
        ctx = executor.run(prep_plan, ctx)

        trace["step_traces"] = ctx.step_traces
        trace["rewrite"] = ctx.outputs.get("_rewrite", {})
        trace["retrieve"] = ctx.outputs.get("_retrieve_info", {})
        trace["evidence"] = ctx.outputs.get("_quality", {})

        if ctx.failed:
            result = self._build_step_failure_result(question, route, plan, ctx, trace)
            yield AnswerStreamEvent(content=result.answer, done=True, result=result)
            return

        if ctx.gated:
            result = self._build_gated_rag_result(question, route, plan, ctx, trace)
            yield AnswerStreamEvent(content=result.answer, done=True, result=result)
            return

        memory = WorkingMemory(question.qid, question.question)
        memory.add_evidence(ctx.evidence)
        cfg = ctx.outputs["_config"]
        tool_report = self.numeric_tools.run(
            question,
            ctx.evidence,
            enabled=bool(cfg.get("use_calculator")),
        )
        ctx.outputs["_tool_report"] = tool_report.to_dict()
        ctx.outputs["_tool_context"] = tool_report.context_block
        trace["tools"] = tool_report.to_dict()
        context_note = "\n\n".join(
            part for part in [_history_note(cfg["history"]), memory.summary()] if part
        )
        messages = build_open_answer_messages(
            question,
            ctx.evidence,
            context_note=context_note,
            tool_context=tool_report.context_block,
        )

        parts: list[str] = []
        for chunk in self.llm.chat_stream(messages, temperature=0.0):
            if chunk.content:
                parts.append(chunk.content)
                yield AnswerStreamEvent(content=chunk.content)

        answer_text = "".join(parts).strip()
        citation_report = self.citation_validator.validate(answer_text, ctx.evidence)
        ctx.answer_text = citation_report.corrected_answer
        ctx.outputs["_citation_report"] = citation_report
        ctx.outputs["_memory"] = memory.to_dict()
        trace["citations"] = citation_report.to_dict()

        usage = TokenUsage(
            prompt_tokens=max(1, sum(len(m.get("content", "")) for m in messages) // 2),
            completion_tokens=max(1, len(answer_text) // 2),
        )
        result = self._build_rag_result(question, route, plan, ctx, trace, usage=usage)
        self.agent_runtime.store_cache(question, result, mode=mode, history=history)
        yield AnswerStreamEvent(done=True, result=result)

    def _prepare_rag_context(
        self,
        question: Question,
        route: Any,
        plan: AgentPlan,
        *,
        history: str,
        history_entities: dict[str, Any],
        trace: dict[str, Any],
        mode: str,
        run_ctx: Any | None = None,
    ) -> tuple[StepContext, Any, AgentPlan, dict[str, Any]]:
        bm25_w = self.settings.bm25_channel_weight
        faiss_w = self.settings.vector_channel_weight
        if mode == "bm25":
            bm25_w, faiss_w = 1.5, 0.0
        elif mode == "naive":
            bm25_w, faiss_w = 1.0, 0.45
        if not self.settings.enable_vector_retrieval:
            faiss_w = 0.0

        budget = run_ctx.budget if run_ctx is not None else None
        evidence_top_k = budget.evidence_top_k if budget else self.evidence_top_k
        max_evidence_chars = budget.max_evidence_chars if budget else self.max_evidence_chars
        rerank_top_k = budget.rerank_top_k if budget else max(
            self.evidence_top_k * self.rerank_top_k_multiplier, self.evidence_top_k
        )

        filter_doc_ids = set(question.doc_ids) if question.doc_ids else None
        ctx = StepContext(
            question_text=question.question,
            route=route.route.value,
            plan_steps=[s.action for s in plan.steps],
        )
        ctx.outputs["_config"] = {
            "bm25_w": bm25_w,
            "faiss_w": faiss_w,
            "rerank_top_k": rerank_top_k,
            "evidence_top_k": evidence_top_k,
            "max_evidence_chars": max_evidence_chars,
            "filter_doc_ids": filter_doc_ids,
            "history": history,
            "history_entities": history_entities,
            "use_calculator": bool(run_ctx.intent.use_calculator) if run_ctx else False,
            "enable_vector": self.settings.enable_vector_retrieval and faiss_w > 0,
        }
        return ctx, route, plan, trace

    def _kb_scope_warnings(self, question: Question) -> list[str]:
        if not self.settings.require_kb_scope_for_rag:
            return []
        meta = question.metadata or {}
        if meta.get("kb_id") or meta.get("kb_ids") or question.doc_ids:
            return []
        return ["kb_scope_missing"]

    def _build_scope_warning_result(
        self,
        question: Question,
        route: Any,
        plan: AgentPlan,
        trace: dict[str, Any],
        warnings: list[str],
    ) -> AnswerResult:
        return AnswerResult(
            qid=question.qid,
            answer="请先选择知识库后再提问，以便在正确的文档范围内检索。",
            domain=question.domain,
            answer_format="open",
            confidence=0.0,
            evidence=[],
            token_usage=TokenUsage(),
            metadata={
                "strategy": "kb_scope_required",
                "route": route.to_dict(),
                "plan": plan.to_dict(),
                "warnings": warnings,
                "gated": True,
                "trace": trace,
            },
        )

    def _build_step_failure_result(
        self,
        question: Question,
        route: Any,
        plan: AgentPlan,
        ctx: StepContext,
        trace: dict[str, Any],
    ) -> AnswerResult:
        return AnswerResult(
            qid=question.qid,
            answer="处理问题时发生内部错误，请稍后重试。",
            domain=question.domain,
            answer_format="open",
            confidence=0.0,
            evidence=ctx.evidence,
            token_usage=TokenUsage(),
            metadata={
                "strategy": "agentic_rag_failed",
                "route": route.to_dict(),
                "plan": plan.to_dict(),
                "error": ctx.failure_error,
                "step_traces": ctx.step_traces,
                "trace": trace,
            },
        )

    def _build_gated_rag_result(
        self, question: Question, route: Any, plan: AgentPlan, ctx: StepContext, trace: dict[str, Any]
    ) -> AnswerResult:
        quality = ctx.quality_report
        return AnswerResult(
            qid=question.qid,
            answer=_REFUSAL_ANSWER,
            domain=question.domain,
            answer_format="open",
            confidence=0.0,
            evidence=ctx.evidence,
            token_usage=TokenUsage(),
            metadata={
                "strategy": "gated_rag",
                "route": route.to_dict(),
                "plan": plan.to_dict(),
                "evidence_quality": quality.to_dict() if quality else {},
                "risk_flags": getattr(quality, "risk_flags", []),
                "gated": True,
                "trace": trace,
            },
        )

    def _build_rag_result(
        self,
        question: Question,
        route: Any,
        plan: AgentPlan,
        ctx: StepContext,
        trace: dict[str, Any],
        *,
        usage: TokenUsage,
    ) -> AnswerResult:
        citation_report = ctx.outputs.get("_citation_report")
        quality = ctx.quality_report
        answer_text = citation_report.corrected_answer if citation_report else ctx.answer_text
        return AnswerResult(
            qid=question.qid,
            answer=answer_text,
            domain=question.domain,
            answer_format="open",
            confidence=0.0,
            evidence=ctx.evidence,
            token_usage=usage,
            raw_response=ctx.answer_text,
            metadata={
                "strategy": "agentic_rag",
                "route": route.to_dict(),
                "plan": plan.to_dict(),
                "query_rewrite": ctx.outputs.get("_rewrite", {}),
                "conversation_history_used": bool(ctx.outputs["_config"].get("history")),
                "memory": ctx.outputs.get("_memory", {}),
                "evidence_quality": quality.to_dict() if quality else {},
                "risk_flags": getattr(quality, "risk_flags", []),
                "citations": citation_report.structured_citations_for_api() if citation_report else ctx.citations,
                "tool_report": ctx.outputs.get("_tool_report", {}),
                "gated": False,
                "trace": trace,
            },
        )

    def _answer_llm_only(self, question: Question, *, trace: dict[str, Any]) -> AnswerResult:
        messages = [
            {
                "role": "system",
                "content": (
                    "你是长文本智能问答助手。当前为「仅模型回答」模式，"
                    "请直接根据已有知识回答，不需要引用文档。"
                    "若问题需要具体文件中的数据，请说明需要上传相关文档。"
                ),
            },
            {"role": "user", "content": question.question},
        ]
        response = self.llm.chat(messages, temperature=0.3)
        return AnswerResult(
            qid=question.qid,
            answer=response.text.strip(),
            domain=question.domain,
            answer_format="open",
            confidence=1.0,
            evidence=[],
            token_usage=response.usage,
            raw_response=response.text,
            metadata={"strategy": "llm_only", "route": {"route": "llm_only"}, "plan": {}, "gated": False, "trace": trace},
        )

    def _answer_conversational(
        self,
        question: Question,
        route: dict,
        plan: dict,
        *,
        trace: dict[str, Any],
    ) -> AnswerResult:
        messages = [
            {"role": "system", "content": _CONVERSATIONAL_SYSTEM},
            {"role": "user", "content": question.question},
        ]
        response = self.llm.chat(messages, temperature=0.3, max_tokens=256)
        return AnswerResult(
            qid=question.qid,
            answer=response.text.strip(),
            domain=question.domain,
            answer_format="open",
            confidence=1.0,
            evidence=[],
            token_usage=response.usage,
            raw_response=response.text,
            metadata={"strategy": "conversational", "route": route, "plan": plan, "gated": False, "trace": trace},
        )

    def _answer_structured(
        self,
        question: Question,
        route: dict,
        plan: dict,
        *,
        trace: dict[str, Any],
    ) -> AnswerResult:
        total_usage = TokenUsage()
        verdicts = []
        memory = WorkingMemory(question.qid, question.question)
        for claim in self.analyzer.build_claims(question):
            verdict, usage = self.verifier.verify(claim, metadata=question.metadata)
            total_usage.add(usage)
            verdicts.append(verdict)
            memory.add_verdict(verdict)
        answer, confidence = self.assembler.assemble(question, verdicts)

        evidence = []
        seen: set[str] = set()
        for verdict in verdicts:
            for item in verdict.evidence:
                if item.chunk_id not in seen:
                    evidence.append(item)
                    seen.add(item.chunk_id)

        quality = assess_evidence_quality(question, evidence)
        citation_report = self.citation_validator.validate(answer, evidence)
        trace["citations"] = citation_report.to_dict()

        return AnswerResult(
            qid=question.qid,
            answer=citation_report.corrected_answer,
            domain=question.domain,
            answer_format=question.answer_format,
            confidence=confidence,
            evidence=evidence,
            verdicts=verdicts,
            token_usage=total_usage,
            metadata={
                "strategy": "claim_verification",
                "route": route,
                "plan": plan,
                "memory": memory.to_dict(),
                "evidence_quality": quality.to_dict(),
                "risk_flags": quality.risk_flags,
                "citations": citation_report.structured_citations_for_api(),
                "trace": trace,
            },
        )

    def _answer_rag(
        self,
        question: Question,
        route: Any,
        plan: AgentPlan,
        *,
        history: str,
        history_entities: dict[str, Any],
        trace: dict[str, Any],
        mode: str = "auto",
    ) -> AnswerResult:
        run_ctx = self.agent_runtime.prepare_rag_run(question, mode=mode, history=history)
        trace["agent_runtime"] = run_ctx.to_dict()
        if run_ctx.cached_result is not None:
            trace["cache_hit"] = True
            cached = run_ctx.cached_result
            metadata = dict(cached.metadata or {})
            metadata["trace"] = {**(metadata.get("trace") or {}), **trace}
            return replace(cached, metadata=metadata)

        if self.settings.require_kb_scope_for_rag and run_ctx.warnings:
            return self._build_scope_warning_result(question, route, plan, trace, run_ctx.warnings)

        ctx, route, plan, trace = self._prepare_rag_context(
            question,
            route,
            plan,
            history=history,
            history_entities=history_entities,
            trace=trace,
            mode=mode,
            run_ctx=run_ctx,
        )

        executor = self._build_executor(question, run_ctx=run_ctx)
        ctx = executor.run(plan, ctx)

        trace["step_traces"] = ctx.step_traces
        trace["rewrite"] = ctx.outputs.get("_rewrite", {})
        trace["retrieve"] = ctx.outputs.get("_retrieve_info", {})
        trace["evidence"] = ctx.outputs.get("_quality", {})
        citation_report = ctx.outputs.get("_citation_report")
        if citation_report:
            trace["citations"] = citation_report.to_dict()

        if ctx.failed:
            return self._build_step_failure_result(question, route, plan, ctx, trace)

        if ctx.gated:
            return self._build_gated_rag_result(question, route, plan, ctx, trace)

        response = ctx.outputs.get("_llm_response")
        usage = response.usage if response else TokenUsage()
        result = self._build_rag_result(question, route, plan, ctx, trace, usage=usage)
        self.agent_runtime.store_cache(question, result, mode=mode, history=history)
        return result

    def _build_executor(self, question: Question, *, run_ctx: Any | None = None) -> StepExecutor:
        executor = StepExecutor(trace_recorder=self.trace_recorder)

        def handle_rewrite_query(ctx: StepContext) -> StepContext:
            cfg = ctx.outputs["_config"]
            rewrite = self.query_rewriter.rewrite(
                question,
                history=cfg["history"],
                history_entities=cfg["history_entities"] or None,
            )
            ctx.sub_queries = rewrite.sub_queries
            ctx.query_entities = rewrite.query_entities.to_dict()
            ctx.outputs["_rewrite"] = rewrite.to_dict()
            return ctx

        def handle_retrieve(ctx: StepContext) -> StepContext:
            cfg = ctx.outputs["_config"]
            queries = ctx.sub_queries or [question.question]
            retrieve_metadata = dict(question.metadata or {})
            retrieve_metadata["enable_vector_retrieval"] = bool(cfg.get("enable_vector", True))
            retrieved = self.retriever.retrieve_queries(
                queries,
                filter_doc_ids=cfg["filter_doc_ids"],
                source="rag",
                metadata=retrieve_metadata,
                bm25_weight=cfg["bm25_w"],
                faiss_weight=cfg["faiss_w"],
            )
            ctx.retrieved = retrieved
            ctx.outputs["_retrieve_info"] = {
                "query_count": len(queries),
                "retrieved_count": len(retrieved),
                "bm25_weight": cfg["bm25_w"],
                "faiss_weight": cfg["faiss_w"],
            }
            return ctx

        def handle_rerank(ctx: StepContext) -> StepContext:
            cfg = ctx.outputs["_config"]
            reranked, report = self._rerank_with_policy(
                question,
                ctx.retrieved,
                top_k=int(cfg["rerank_top_k"]),
            )
            ctx.reranked = reranked
            ctx.outputs["_rerank_report"] = report
            return ctx

        def handle_select_evidence(ctx: StepContext) -> StepContext:
            cfg = ctx.outputs["_config"]
            evidence_top_k = int(cfg.get("evidence_top_k", self.evidence_top_k))
            max_evidence_chars = int(cfg.get("max_evidence_chars", self.max_evidence_chars))
            doc_ids = list(dict.fromkeys(r.doc_id for r in ctx.reranked))
            if len(doc_ids) > 1:
                raw_evidence = coverage_quota_select(
                    ctx.reranked, top_k=evidence_top_k, doc_ids=doc_ids
                )
            else:
                pseudo_claim = self.analyzer._build_option_claim(question, "open", question.question)
                raw_evidence = select_evidence(
                    pseudo_claim,
                    ctx.reranked,
                    top_k=evidence_top_k,
                    max_chars=max_evidence_chars,
                )
            evidence, compression_report = self.evidence_compressor.compress(
                question, raw_evidence, max_total_chars=max_evidence_chars
            )
            ctx.evidence = evidence
            ctx.outputs["_compression_report"] = compression_report.to_dict()
            return ctx

        def handle_assess_evidence(ctx: StepContext) -> StepContext:
            cfg = ctx.outputs["_config"]
            quality = assess_evidence_quality(question, ctx.evidence)
            retry_report: dict[str, Any] | None = None

            if quality.has_critical_flags():
                gap = quality.gap_summary()
                refined_queries = self.query_rewriter.refine(question, gap=gap, history=cfg["history"])
                retrieve_metadata = dict(question.metadata or {})
                retrieve_metadata["enable_vector_retrieval"] = bool(cfg.get("enable_vector", True))
                retrieved2 = self.retriever.retrieve_queries(
                    refined_queries,
                    filter_doc_ids=cfg["filter_doc_ids"],
                    source="rag_retry",
                    metadata=retrieve_metadata,
                    bm25_weight=cfg["bm25_w"],
                    faiss_weight=cfg["faiss_w"],
                )
                evidence_top_k = int(cfg.get("evidence_top_k", self.evidence_top_k))
                max_evidence_chars = int(cfg.get("max_evidence_chars", self.max_evidence_chars))
                rerank_top_k = int(cfg["rerank_top_k"])
                reranked2, _ = self._rerank_with_policy(question, retrieved2, top_k=rerank_top_k)
                doc_ids2 = list(dict.fromkeys(r.doc_id for r in reranked2))
                if len(doc_ids2) > 1:
                    raw_evidence2 = coverage_quota_select(
                        reranked2, top_k=evidence_top_k, doc_ids=doc_ids2
                    )
                else:
                    pseudo_claim2 = self.analyzer._build_option_claim(question, "open", question.question)
                    raw_evidence2 = select_evidence(
                        pseudo_claim2,
                        reranked2,
                        top_k=evidence_top_k,
                        max_chars=max_evidence_chars,
                    )
                evidence2, _ = self.evidence_compressor.compress(
                    question, raw_evidence2, max_total_chars=max_evidence_chars
                )
                quality2 = assess_evidence_quality(question, evidence2)
                retry_report = quality2.to_dict()
                if quality2.evidence_count > quality.evidence_count:
                    ctx.evidence = evidence2
                    quality = quality2

            ctx.quality_report = quality
            if quality.is_unsatisfactory():
                ctx.gated = True

            ctx.outputs["_quality"] = {
                "quality": quality.to_dict(),
                "retry_triggered": quality.has_critical_flags(),
                "retry_report": retry_report,
                "rerank_report": ctx.outputs.get("_rerank_report", {}),
                "compression_report": ctx.outputs.get("_compression_report", {}),
                "selected_count": len(ctx.evidence),
            }
            return ctx

        def handle_generate_answer(ctx: StepContext) -> StepContext:
            cfg = ctx.outputs["_config"]
            memory = WorkingMemory(question.qid, question.question)
            memory.add_evidence(ctx.evidence)
            context_note = "\n\n".join(
                part for part in [_history_note(cfg["history"]), memory.summary()] if part
            )
            tool_report = self.numeric_tools.run(
                question,
                ctx.evidence,
                enabled=bool(cfg.get("use_calculator")),
            )
            ctx.outputs["_tool_report"] = tool_report.to_dict()
            ctx.outputs["_tool_context"] = tool_report.context_block
            messages = build_open_answer_messages(
                question,
                ctx.evidence,
                context_note=context_note,
                tool_context=tool_report.context_block,
            )
            response = self.llm.chat(messages, temperature=0.0)
            ctx.answer_text = response.text.strip()
            ctx.outputs["_llm_response"] = response
            ctx.outputs["_memory"] = memory.to_dict()
            return ctx

        def handle_validate_citations(ctx: StepContext) -> StepContext:
            citation_report = self.citation_validator.validate(ctx.answer_text, ctx.evidence)
            ctx.citations = citation_report.structured_citations_for_api()
            ctx.answer_text = citation_report.corrected_answer
            ctx.outputs["_citation_report"] = citation_report
            return ctx

        executor.register("rewrite_query", handle_rewrite_query)
        executor.register("hybrid_retrieve", handle_retrieve)
        executor.register("rerank_evidence", handle_rerank)
        executor.register("select_evidence", handle_select_evidence)
        executor.register("assess_evidence", handle_assess_evidence)
        executor.register("generate_answer", handle_generate_answer)
        executor.register("validate_citations", handle_validate_citations)

        return executor

    def _rerank_with_policy(
        self,
        question: Question,
        candidates: list[Any],
        *,
        top_k: int,
    ) -> tuple[list[Any], dict[str, Any]]:
        from finlongrag.retrieval.rerank import RerankReport

        trigger_info: dict[str, Any] = {"conditional_rerank_enabled": self.settings.conditional_rerank_enabled}
        do_rerank = True
        if self.settings.conditional_rerank_enabled:
            do_rerank, trigger_info = should_rerank(
                candidates,
                threshold=self.settings.rerank_trigger_threshold,
            )
        if do_rerank:
            try:
                reranked, rerank_report = self.evidence_reranker.rerank(question, candidates, top_k=top_k)
                trigger_info["applied"] = True
                return reranked, {**rerank_report.to_dict(), "trigger": trigger_info}
            except Exception as exc:
                reranked = sorted(candidates, key=lambda item: item.score, reverse=True)[:top_k]
                trigger_info = {
                    **trigger_info,
                    "applied": False,
                    "fallback": "retrieval_score_sort",
                    "error": f"{type(exc).__name__}: {exc}",
                }
        else:
            reranked = sorted(candidates, key=lambda item: item.score, reverse=True)[:top_k]
            trigger_info["applied"] = False
        rerank_report = RerankReport(
            candidate_count=len(candidates),
            selected_count=len(reranked),
            covered_doc_ids=list(dict.fromkeys(item.doc_id for item in reranked)),
            scoring=[],
        )
        return reranked, {**rerank_report.to_dict(), "trigger": trigger_info}


def _history_note(history: str) -> str:
    if not history:
        return ""
    return "[会话上下文]\n" + history[:2000]
