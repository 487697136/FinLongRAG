"""Reasoning pipeline for one question."""

from __future__ import annotations

from finlongrag.agent.memory import WorkingMemory
from finlongrag.agent.planner import AgentPlanner
from finlongrag.agent.router import AgentRouter, RouteType
from finlongrag.core.config import Settings
from finlongrag.core.schema import AnswerResult, Question, TokenUsage
from finlongrag.reasoning.analyzer import QuestionAnalyzer
from finlongrag.reasoning.assembler import AnswerAssembler
from finlongrag.reasoning.evidence_compressor import EvidenceCompressor
from finlongrag.reasoning.fact_ledger import compile_numeric_fact_ledger, format_fact_ledger
from finlongrag.reasoning.llm import ChatModel
from finlongrag.reasoning.prompts import build_open_answer_messages
from finlongrag.reasoning.query_rewrite import QueryRewriter
from finlongrag.reasoning.verifier import ClaimVerifier
from finlongrag.retrieval.evidence import select_evidence
from finlongrag.retrieval.quality import assess_evidence_quality
from finlongrag.retrieval.rerank import DashScopeEvidenceReranker, create_evidence_reranker
from finlongrag.retrieval.retriever import Retriever


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
    ) -> None:
        self.settings = settings or Settings.from_file()
        self.retriever = retriever
        self.llm = llm
        self.router = AgentRouter()
        self.planner = AgentPlanner()
        self.analyzer = QuestionAnalyzer()
        self.assembler = AnswerAssembler()
        self.query_rewriter = QueryRewriter()
        self.evidence_reranker = evidence_reranker or create_evidence_reranker(self.settings)
        self.evidence_compressor = EvidenceCompressor()
        self.evidence_top_k = evidence_top_k
        self.max_evidence_chars = max_evidence_chars
        self.rerank_top_k_multiplier = max(1, self.settings.rerank_top_k_multiplier)
        self.verifier = ClaimVerifier(
            retriever,
            llm,
            evidence_per_claim=evidence_per_claim,
            evidence_chars_per_claim=evidence_chars_per_claim,
        )

    def answer(self, question: Question, *, history: str = "") -> AnswerResult:
        route = self.router.decide(question)
        plan = self.planner.build(question, route)
        if route.route == RouteType.CLAIM_VERIFICATION and question.options and question.answer_format in {"mcq", "multi", "tf"}:
            return self._answer_structured(question, route.to_dict(), plan.to_dict())
        return self._answer_open(question, route.to_dict(), plan.to_dict(), history=history)

    def _answer_structured(self, question: Question, route: dict, plan: dict) -> AnswerResult:
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
        ledger = compile_numeric_fact_ledger(question, evidence)
        return AnswerResult(
            qid=question.qid,
            answer=answer,
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
                "numeric_fact_ledger": ledger,
                "risk_flags": quality.risk_flags,
            },
        )

    def _answer_open(self, question: Question, route: dict, plan: dict, *, history: str = "") -> AnswerResult:
        rewrite = self.query_rewriter.rewrite(question, history=history)
        filter_doc_ids = set(question.doc_ids) if question.doc_ids else None
        retrieved = self.retriever.retrieve_queries(
            rewrite.sub_queries,
            filter_doc_ids=filter_doc_ids,
            source="open_query_rewrite",
            metadata=question.metadata,
        )
        reranked, rerank_report = self.evidence_reranker.rerank(
            question,
            retrieved,
            top_k=max(self.evidence_top_k * self.rerank_top_k_multiplier, self.evidence_top_k),
        )
        pseudo_claim = self.analyzer._build_option_claim(question, "open", question.question)
        raw_evidence = select_evidence(
            pseudo_claim,
            reranked,
            top_k=self.evidence_top_k,
            max_chars=self.max_evidence_chars,
        )
        evidence, compression_report = self.evidence_compressor.compress(
            question,
            raw_evidence,
            max_total_chars=self.max_evidence_chars,
        )
        quality = assess_evidence_quality(question, evidence)
        ledger = compile_numeric_fact_ledger(question, evidence)
        memory = WorkingMemory(question.qid, question.question)
        memory.add_evidence(evidence)
        context_note = "\n\n".join(
            part
            for part in [_history_note(history), memory.summary(), format_fact_ledger(ledger)]
            if part
        )
        response = self.llm.chat(build_open_answer_messages(question, evidence, context_note=context_note), temperature=0.0)
        return AnswerResult(
            qid=question.qid,
            answer=response.text.strip(),
            domain=question.domain,
            answer_format="open",
            confidence=0.0,
            evidence=evidence,
            token_usage=response.usage,
            raw_response=response.text,
            metadata={
                "strategy": "grounded_open_qa",
                "route": route,
                "plan": plan,
                "query_rewrite": rewrite.to_dict(),
                "conversation_history_used": bool(history),
                "rerank_report": rerank_report.to_dict(),
                "compression_report": compression_report.to_dict(),
                "memory": memory.to_dict(),
                "evidence_quality": quality.to_dict(),
                "numeric_fact_ledger": ledger,
                "risk_flags": quality.risk_flags,
            },
        )


def _history_note(history: str) -> str:
    if not history:
        return ""
    return "[会话上下文]\n" + history[:2000]
