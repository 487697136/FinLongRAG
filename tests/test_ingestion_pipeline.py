"""Tests for stage-based ingestion pipeline."""

from __future__ import annotations

from pathlib import Path

from finlongrag.core.schema import Document
from finlongrag.ingestion.pipeline import IngestionPipeline


def test_ingestion_pipeline_runs_parse_and_chunk_stages(tmp_path: Path):
    text_file = tmp_path / "sample.txt"
    text_file.write_text("第一章 概述\n\n营业收入持续增长。\n\n第二章 财务\n\n净利润 10 亿元。", encoding="utf-8")
    document = Document(
        doc_id="doc1",
        title="sample",
        domain="financial_reports",
        path=str(text_file),
        metadata={"file_type": "txt"},
    )
    pipeline = IngestionPipeline()
    ctx = pipeline.run(kb_id="kb1", document_id="doc1", document=document)
    assert not ctx.error
    assert ctx.parsed_document is not None
    assert ctx.chunks
    stage_names = [report["stage"] for report in ctx.stage_reports]
    assert stage_names == ["parse", "chunk"]
