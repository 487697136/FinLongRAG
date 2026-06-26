from decimal import Decimal

from finlongrag.core.schema import Question, RetrievalResult
from finlongrag.reasoning.fact_ledger import compile_numeric_fact_ledger
from finlongrag.reasoning.query_rewrite import QueryRewriter
from finlongrag.reasoning.tools import SafeCalculator, compare_values, growth_rate
from finlongrag.retrieval.quality import assess_evidence_quality


def _evidence():
    return [
        RetrievalResult(
            chunk_id="c1",
            doc_id="doc1",
            domain="financial_reports",
            evidence_text="营业收入 2025年 120亿元，2024年 100亿元。",
            score=1.0,
            source="test",
            query="营业收入",
            metadata={
                "page": 1,
                "section": "主要财务指标",
                "numbers": ["2025年", "120亿元", "2024年", "100亿元"],
                "dates": ["2025年", "2024年"],
                "chunk_type": "table_row",
            },
        )
    ]


def test_query_rewrite_and_quality_report_are_deterministic():
    question = Question(
        qid="q1",
        domain="financial_reports",
        question="2025年营业收入相比2024年增长了吗？",
        doc_ids=["doc1"],
    )

    rewrite = QueryRewriter().rewrite(question)
    quality = assess_evidence_quality(question, _evidence())

    assert "营业收入" in rewrite.rewritten
    assert quality.coverage_ratio > 0
    assert quality.has_structured_evidence
    assert not quality.missing_doc_ids


def test_fact_ledger_extracts_normalized_financial_values():
    question = Question(qid="q1", question="营业收入是多少？", domain="financial_reports")

    ledger = compile_numeric_fact_ledger(question, _evidence())

    assert ledger["fact_count"] >= 2
    assert any(fact["normalized_value"] == "12000000000" for fact in ledger["facts"])


def test_safe_calculator_allows_arithmetic_and_blocks_names():
    calculator = SafeCalculator()

    assert calculator.evaluate("(120 - 100) / 100") == Decimal("0.2")
    assert compare_values("120", "100") == "gt"
    assert growth_rate("120", "100") == Decimal("0.2")

    try:
        calculator.evaluate("__import__('os').system('echo bad')")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe expression should be rejected")

