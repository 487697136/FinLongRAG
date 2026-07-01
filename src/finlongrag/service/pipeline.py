"""Public FinLongRAG service facade."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

from finlongrag.core.config import Settings
from finlongrag.core.schema import AnswerResult, Question
from finlongrag.framework.trace import TraceRecorder, trace_run
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.document import DocumentIndex
from finlongrag.index.faiss_store import create_configured_vector_store
from finlongrag.index.providers import create_embedding_provider
from finlongrag.reasoning.llm import QwenChatModel, llm_model_scope
from finlongrag.reasoning.pipeline import ReasoningPipeline
from finlongrag.reasoning.streaming import AnswerStreamEvent
from finlongrag.retrieval.retriever import Retriever
from finlongrag.storage.knowledge_repository import create_knowledge_repository

logger = logging.getLogger(__name__)


class FinLongRAGPipeline:
    """Main backend entry point for product and CLI callers."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        index_path: Path | None = None,
        doc_index_path: Path | None = None,
        dry_run: bool = False,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self.settings = settings or Settings.from_file()
        self.settings.ensure_dirs()

        # Use smart index resolution: global merge → active KB version → legacy fallback
        index_path, doc_index_path, self.index_version = _resolve_index_paths(
            self.settings, index_path=index_path, doc_index_path=doc_index_path
        )
        self.index_path = index_path
        self.doc_index_path = doc_index_path
        self.trace_recorder = trace_recorder or TraceRecorder(self.settings.output_dir / "traces.jsonl")
        self.index = _load_bm25_or_empty(self.index_path, tokenizer_mode=self.settings.tokenizer_mode)
        self.doc_index = _load_document_index_or_empty(self.doc_index_path, tokenizer_mode=self.settings.tokenizer_mode)
        self.vector_store = create_configured_vector_store(self.settings, kb_id=None)  # Search all KBs
        self.vector_provider = create_embedding_provider(self.settings)
        self.retriever = Retriever(
            self.index,
            self.doc_index,
            top_k_per_query=self.settings.top_k_per_query,
            fused_top_k=self.settings.fused_top_k,
            blind_top_docs=self.settings.blind_top_docs,
            scoring_mode=self.settings.scoring_mode,
            vector_provider=self.vector_provider,
            vector_store=self.vector_store,
            bm25_channel_weight=self.settings.bm25_channel_weight,
            vector_channel_weight=self.settings.vector_channel_weight,
        )
        self.llm = QwenChatModel(self.settings, dry_run=dry_run)
        self.reasoning = ReasoningPipeline(
            self.retriever,
            self.llm,
            evidence_top_k=self.settings.evidence_top_k,
            max_evidence_chars=self.settings.max_evidence_chars,
            evidence_per_claim=self.settings.evidence_per_claim,
            evidence_chars_per_claim=self.settings.evidence_chars_per_claim,
            settings=self.settings,
            trace_recorder=self.trace_recorder,
        )

    def clear_runtime_cache(self) -> None:
        self.reasoning.agent_runtime.clear_cache()

    def answer(
        self,
        question: Question,
        *,
        history: str = "",
        history_entities: dict | None = None,
        mode: str = "auto",
        llm_model: str | None = None,
    ) -> AnswerResult:
        with llm_model_scope(llm_model), trace_run(
            "finlongrag-answer",
            self.trace_recorder,
            qid=question.qid,
            domain=question.domain,
            answer_format=question.answer_format,
        ) as run:
            result = self.reasoning.answer(
                question,
                history=history,
                history_entities=history_entities or {},
                mode=mode,
            )
            result.metadata.setdefault("trace_id", run.trace_id)
            if self.index_version:
                result.metadata.setdefault("index_version", self.index_version)
            if llm_model:
                result.metadata.setdefault("llm_model", llm_model)
            return result

    def ask(
        self,
        text: str,
        *,
        domain: str = "",
        doc_ids: list[str] | None = None,
        kb_id: str | None = None,
        kb_ids: list[str] | None = None,
        qid: str = "adhoc",
        history: str = "",
        history_entities: dict | None = None,
        mode: str = "auto",
        top_k: int | None = None,
        llm_model: str | None = None,
    ) -> AnswerResult:
        question = _build_question(
            text,
            domain=domain,
            doc_ids=doc_ids,
            kb_id=kb_id,
            kb_ids=kb_ids,
            top_k=top_k,
            qid=qid,
        )
        return self.answer(
            question,
            history=history,
            history_entities=history_entities,
            mode=mode,
            llm_model=llm_model,
        )

    def answer_stream(
        self,
        question: Question,
        *,
        history: str = "",
        history_entities: dict | None = None,
        mode: str = "auto",
        llm_model: str | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        with llm_model_scope(llm_model), trace_run(
            "finlongrag-answer-stream",
            self.trace_recorder,
            qid=question.qid,
            domain=question.domain,
            answer_format=question.answer_format,
        ) as run:
            for event in self.reasoning.answer_stream(
                question,
                history=history,
                history_entities=history_entities or {},
                mode=mode,
            ):
                if event.done and event.result is not None:
                    event.result.metadata.setdefault("trace_id", run.trace_id)
                    if self.index_version:
                        event.result.metadata.setdefault("index_version", self.index_version)
                    if llm_model:
                        event.result.metadata.setdefault("llm_model", llm_model)
                yield event

    def ask_stream(
        self,
        text: str,
        *,
        domain: str = "",
        doc_ids: list[str] | None = None,
        kb_id: str | None = None,
        kb_ids: list[str] | None = None,
        qid: str = "adhoc",
        history: str = "",
        history_entities: dict | None = None,
        mode: str = "auto",
        top_k: int | None = None,
        llm_model: str | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        question = _build_question(
            text,
            domain=domain,
            doc_ids=doc_ids,
            kb_id=kb_id,
            kb_ids=kb_ids,
            top_k=top_k,
            qid=qid,
        )
        yield from self.answer_stream(
            question,
            history=history,
            history_entities=history_entities,
            mode=mode,
            llm_model=llm_model,
        )


def _build_question(
    text: str,
    *,
    domain: str,
    doc_ids: list[str] | None,
    kb_id: str | None,
    kb_ids: list[str] | None,
    top_k: int | None,
    qid: str,
) -> Question:
    question = Question(
        qid=qid,
        question=text,
        domain=domain,
        doc_ids=doc_ids or [],
        answer_format="open",
    )
    metadata: dict[str, object] = {}
    if top_k is not None:
        metadata["top_k"] = max(1, min(int(top_k), 50))
    if kb_ids:
        metadata["kb_ids"] = kb_ids
        if len(kb_ids) == 1:
            metadata["kb_id"] = kb_ids[0]
    elif kb_id:
        metadata["kb_id"] = kb_id
    if metadata:
        question.metadata = metadata
    return question


def _resolve_index_paths(
    settings: Settings,
    *,
    index_path: Path | None,
    doc_index_path: Path | None,
) -> tuple[Path, Path, dict[str, object] | None]:
    if index_path is not None:
        return index_path, doc_index_path or settings.index_dir / "document_index.pkl", None

    # Priority 1: Use global merged indexes for multi-KB support
    global_bm25 = settings.index_dir / "bm25_index_global.pkl"
    global_doc = settings.index_dir / "document_index_global.pkl"

    if global_bm25.exists() and global_doc.exists():
        logger.info("Loading global indexes: %s", global_bm25)
        return global_bm25, global_doc, {"type": "global", "kb_id": None}

    # Priority 2: legacy single-KB files only when explicitly present on disk.
    # Do not pick an arbitrary active version across knowledge bases.
    legacy_bm25 = settings.index_dir / "bm25_index.pkl"
    legacy_doc = settings.index_dir / "document_index.pkl"
    if legacy_bm25.exists() and legacy_doc.exists():
        logger.info("Loading legacy index paths: %s", legacy_bm25)
        return legacy_bm25, legacy_doc, None

    logger.info("No global or legacy indexes found; using empty in-memory indexes")
    return legacy_bm25, legacy_doc, None


def _load_bm25_or_empty(path: Path, *, tokenizer_mode: str) -> BM25FIndex:
    if path.exists():
        return BM25FIndex.load(path)
    return BM25FIndex.build([], tokenizer_mode=tokenizer_mode)


def _load_document_index_or_empty(path: Path, *, tokenizer_mode: str) -> DocumentIndex:
    if path.exists():
        return DocumentIndex.load(path)
    return DocumentIndex.build([], tokenizer_mode=tokenizer_mode)
