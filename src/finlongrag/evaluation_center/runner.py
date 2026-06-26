"""Evaluation runner that uses FinLongRAG's own retrieval stack."""

from __future__ import annotations

from datetime import UTC, datetime

from finlongrag.core.schema import Question
from finlongrag.evaluation_center.metrics import compute_metrics
from finlongrag.evaluation_center.schemas import EvalConfig, EvalItemResult, EvalReport, RetrievalStrategy, TestSet
from finlongrag.service.pipeline import FinLongRAGPipeline


def run_retrieval_evaluation(
    *,
    pipeline: FinLongRAGPipeline,
    config: EvalConfig,
    test_set: TestSet,
    kb_name: str = "",
    progress_callback=None,
) -> EvalReport:
    report = EvalReport(
        id="",
        kb_id=config.kb_id,
        kb_name=kb_name,
        test_set_id=config.test_set_id,
        test_set_name=test_set.name,
        strategy=config.strategy.value,
        top_k=config.top_k,
        status="running",
        progress_total=test_set.count,
        created_at=_now(),
    )
    details: list[EvalItemResult] = []
    try:
        for index, item in enumerate(test_set.items, start=1):
            if progress_callback:
                progress_callback(index, test_set.count)
            results = pipeline.retriever.retrieve_question(
                Question(
                    qid=f"eval_{config.test_set_id}_{index}",
                    question=item.question,
                    answer_format="open",
                    metadata={"kb_id": config.kb_id},
                ),
                restrict_to_doc_ids=False,
            )[: config.top_k]
            details.append(_judge(item.question, item.answer, item.source, results, config.strategy))
        report.details = details
        report.metrics = compute_metrics(details)
        report.progress_current = test_set.count
        report.status = "done"
    except Exception as exc:
        report.status = "failed"
        report.error_message = str(exc)
    finally:
        report.finished_at = _now()
    return report


def _judge(question: str, expected_answer: str, expected_source: str, results, strategy: RetrievalStrategy) -> EvalItemResult:
    expected_source_norm = _norm(expected_source)
    expected_answer_norm = _norm(expected_answer)
    sources = [
        {
            "rank": rank,
            "chunk_id": result.chunk_id,
            "doc_id": result.doc_id,
            "source": result.source,
            "score": result.score,
            "text": result.evidence_text[:300],
        }
        for rank, result in enumerate(results, start=1)
        if strategy != RetrievalStrategy.vector or "vector" in str(result.source).lower()
    ]
    for rank, result in enumerate(results, start=1):
        text_norm = _norm(result.evidence_text)
        doc_norm = _norm(result.doc_id)
        source_hit = bool(expected_source_norm and (expected_source_norm in text_norm or expected_source_norm in doc_norm))
        answer_hit = bool(expected_answer_norm and expected_answer_norm in text_norm)
        if source_hit or answer_hit:
            return EvalItemResult(
                question=question,
                expected_source=expected_source,
                expected_answer=expected_answer,
                hit=True,
                rank=rank,
                matched_chunk=result.evidence_text[:300],
                score=float(result.score),
                sources=sources,
            )
    return EvalItemResult(
        question=question,
        expected_source=expected_source,
        expected_answer=expected_answer,
        hit=False,
        sources=sources,
    )


def _norm(value: str) -> str:
    return "".join(str(value or "").lower().split())


def _now() -> str:
    return datetime.now(UTC).isoformat()

