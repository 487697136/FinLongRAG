"""Public FinLongRAG service facade."""

from __future__ import annotations

from pathlib import Path

from finlongrag.core.config import Settings
from finlongrag.core.schema import AnswerResult, Question
from finlongrag.framework.trace import TraceRecorder, trace_run
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.document import DocumentIndex
from finlongrag.index.faiss_store import create_configured_vector_store
from finlongrag.index.providers import create_embedding_provider
from finlongrag.reasoning.llm import QwenChatModel
from finlongrag.reasoning.pipeline import ReasoningPipeline
from finlongrag.retrieval.retriever import Retriever
from finlongrag.storage.knowledge_repository import create_knowledge_repository


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
        self.index_version: dict[str, object] | None = None

        # Force use of global merged indexes for multi-KB support
        if index_path is None:
            index_path = self.settings.index_dir / "bm25_index_global.pkl"
        if doc_index_path is None:
            doc_index_path = self.settings.index_dir / "document_index_global.pkl"

        self.index_path = index_path
        self.doc_index_path = doc_index_path
        self.index_version = None  # Global index has no single version
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
        )

    def answer(self, question: Question, *, history: str = "") -> AnswerResult:
        with trace_run(
            "finlongrag-answer",
            self.trace_recorder,
            qid=question.qid,
            domain=question.domain,
            answer_format=question.answer_format,
        ) as run:
            result = self.reasoning.answer(question, history=history)
            result.metadata.setdefault("trace_id", run.trace_id)
            if self.index_version:
                result.metadata.setdefault("index_version", self.index_version)
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
    ) -> AnswerResult:
        question = Question(
            qid=qid,
            question=text,
            domain=domain,
            doc_ids=doc_ids or [],
            answer_format="open",
        )
        # 处理多知识库融合或单知识库隔离
        if kb_ids:
            question.metadata = {"kb_ids": kb_ids}
        elif kb_id:
            question.metadata = {"kb_id": kb_id}
        return self.answer(question, history=history)


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
        print(f"[INFO] Loading global indexes: {global_bm25}")
        return global_bm25, global_doc, {"type": "global", "kb_id": None}

    # Priority 2: Try single KB active version (legacy)
    active_version = _load_active_index_version(settings)
    if active_version:
        chunk_path = Path(str(active_version["chunk_index_path"]))
        document_path = Path(str(active_version["document_index_path"]))
        if chunk_path.exists() and document_path.exists():
            print(f"[INFO] Loading single KB index: {chunk_path}")
            return chunk_path, document_path, active_version

    # Priority 3: Fallback to legacy paths
    print(f"[INFO] Fallback to legacy index paths")
    return (
        settings.index_dir / "bm25_index.pkl",
        doc_index_path or settings.index_dir / "document_index.pkl",
        None,
    )


def _load_active_index_version(settings: Settings) -> dict[str, object] | None:
    try:
        repository = create_knowledge_repository(settings.database_url)
        record = repository.get_active_index_version()
    except Exception:
        return None
    return record.to_dict() if record else None


def _load_bm25_or_empty(path: Path, *, tokenizer_mode: str) -> BM25FIndex:
    if path.exists():
        return BM25FIndex.load(path)
    return BM25FIndex.build([], tokenizer_mode=tokenizer_mode)


def _load_document_index_or_empty(path: Path, *, tokenizer_mode: str) -> DocumentIndex:
    if path.exists():
        return DocumentIndex.load(path)
    return DocumentIndex.build([], tokenizer_mode=tokenizer_mode)
