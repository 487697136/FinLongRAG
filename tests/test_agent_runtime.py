"""Tests for engineering-oriented agent runtime features."""

from __future__ import annotations

from finlongrag.agent.intent_resolver import IntentResolver
from finlongrag.agent.query_cache import QueryAnswerCache
from finlongrag.agent.token_budget import allocate_evidence_budget
from finlongrag.agent.tools import NumericToolRunner
from finlongrag.core.config import Settings
from finlongrag.core.schema import AnswerResult, Question, TokenUsage
from finlongrag.retrieval.rerank import should_rerank
from finlongrag.core.schema import RetrievalResult


def test_intent_resolver_detects_financial_metrics_intent():
    resolver = IntentResolver()
    question = Question(qid="q1", question="2025年营业收入同比增长多少？", domain="financial_reports")
    resolution = resolver.resolve(question)
    assert resolution.use_calculator is True
    assert resolution.intents
    assert resolution.intents[0].intent_id == "financial_metrics"


def test_query_cache_hit_for_same_question():
    cache = QueryAnswerCache(max_entries=8, ttl_seconds=600)
    question = Question(
        qid="q1",
        question="净利润是多少？",
        metadata={"kb_id": "kb1"},
    )
    result = AnswerResult(
        qid="q1",
        answer="30亿元",
        domain="",
        answer_format="open",
        confidence=1.0,
        token_usage=TokenUsage(),
    )
    cache.store(question, result, mode="naive")
    lookup, cached = cache.lookup(question, mode="naive")
    assert lookup.hit is True
    assert cached is not None
    assert cached.answer == "30亿元"


def test_should_rerank_skips_when_score_gap_is_large():
    candidates = [
        RetrievalResult(chunk_id=f"c{i}", doc_id="d1", domain="", evidence_text="x", score=score, source="t", query="q")
        for i, score in enumerate([10.0, 8.0, 7.5, 7.0, 6.8, 6.0], start=1)
    ]
    do_rerank, info = should_rerank(candidates, threshold=0.15)
    assert do_rerank is False
    assert info["reason"] == "score_gap_sufficient"


def test_query_cache_separates_different_top_k():
    cache = QueryAnswerCache(max_entries=8, ttl_seconds=600)
    q5 = Question(qid="q1", question="net profit?", metadata={"kb_id": "kb1", "top_k": 5})
    q20 = Question(qid="q1", question="net profit?", metadata={"kb_id": "kb1", "top_k": 20})
    result = AnswerResult(qid="q1", answer="30", domain="", answer_format="open", token_usage=TokenUsage())

    cache.store(q5, result, mode="auto")
    lookup, cached = cache.lookup(q20, mode="auto")

    assert lookup.hit is False
    assert cached is None


def test_should_rerank_triggers_when_top_scores_are_close():
    candidates = [
        RetrievalResult(chunk_id=f"c{i}", doc_id="d1", domain="", evidence_text="x", score=score, source="t", query="q")
        for i, score in enumerate([10.0, 9.8, 9.7, 9.6, 9.5, 9.0], start=1)
    ]
    do_rerank, info = should_rerank(candidates, threshold=0.15)
    assert do_rerank is True
    assert info["reason"] == "score_gap_narrow"


def test_numeric_tool_runner_builds_calc_context():
    settings = Settings.from_file()
    runner = NumericToolRunner()
    question = Question(qid="q1", question="2025年营业收入相比2024年增长了多少？", domain="financial_reports")
    evidence = [
        RetrievalResult(
            chunk_id="c1",
            doc_id="d1",
            domain="financial_reports",
            evidence_text="营业收入 2025年 120亿元，2024年 100亿元。",
            score=1.0,
            source="test",
            query="营业收入",
            metadata={"numbers": ["2025年", "120亿元", "2024年", "100亿元"]},
        )
    ]
    report = runner.run(question, evidence, enabled=True)
    assert report.fact_count >= 2
    assert "数值事实账本" in report.context_block or "calculation_result" in report.context_block


def test_allocate_evidence_budget_trims_for_long_history():
    settings = Settings.from_file()
    budget = allocate_evidence_budget(settings, history_chars=5000)
    assert budget.max_evidence_chars < settings.max_evidence_chars


def test_dense_evidence_budget_keeps_rerank_above_evidence_target():
    settings = Settings.from_file()
    budget = allocate_evidence_budget(settings, intent={"dense_evidence": True})

    assert budget.evidence_top_k >= settings.evidence_top_k
    assert budget.rerank_top_k >= budget.evidence_top_k
