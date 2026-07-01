"""Stage-based document ingestion pipeline (orchestrated, observable)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from finlongrag.core.config import Settings
from finlongrag.core.schema import Chunk, Document
from finlongrag.ingestion.chunker import chunk_document
from finlongrag.ingestion.parser import parse_document

logger = logging.getLogger(__name__)

StageHandler = Callable[["IngestionStageContext"], None]


@dataclass
class IngestionStageContext:
    settings: Settings
    kb_id: str
    document_id: str
    document: Document
    pages: list[Any] = field(default_factory=list)
    parsed_document: Document | None = None
    chunks: list[Chunk] = field(default_factory=list)
    stage_reports: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def record(self, stage: str, **data: Any) -> None:
        self.stage_reports.append({"stage": stage, **data})


@dataclass(frozen=True)
class IngestionStage:
    name: str
    handler: StageHandler


class IngestionPipeline:
    """Explicit ingestion stages inspired by ragent's DAG, kept linear for product maintainability."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_file()
        self.stages: list[IngestionStage] = [
            IngestionStage("parse", _stage_parse),
            IngestionStage("chunk", _stage_chunk),
        ]

    def run(self, *, kb_id: str, document_id: str, document: Document) -> IngestionStageContext:
        ctx = IngestionStageContext(
            settings=self.settings,
            kb_id=kb_id,
            document_id=document_id,
            document=document,
        )
        for stage in self.stages:
            started = perf_counter()
            try:
                stage.handler(ctx)
                duration_ms = int((perf_counter() - started) * 1000)
                ctx.record(f"{stage.name}_timing", duration_ms=duration_ms)
                if ctx.error:
                    break
            except Exception as exc:
                duration_ms = int((perf_counter() - started) * 1000)
                ctx.record(f"{stage.name}_timing", duration_ms=duration_ms, failed=True)
                ctx.error = f"{stage.name}: {exc}"
                logger.exception("Ingestion stage %s failed for document %s", stage.name, document_id)
                break
        return ctx


def _stage_parse(ctx: IngestionStageContext) -> None:
    parsed, pages = parse_document(ctx.document, settings=ctx.settings)
    ctx.parsed_document = parsed
    ctx.pages = pages
    ctx.record("parse", page_count=len(pages), parser=parsed.metadata.get("parser", ""))


def _stage_chunk(ctx: IngestionStageContext) -> None:
    if ctx.parsed_document is None:
        ctx.error = "chunk: parsed document missing"
        return
    chunks = chunk_document(ctx.parsed_document, ctx.pages)
    ctx.chunks = chunks
    ctx.record("chunk", chunk_count=len(chunks))
