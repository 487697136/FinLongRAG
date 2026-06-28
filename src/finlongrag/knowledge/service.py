"""Knowledge base management and ingestion service."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from finlongrag.core.config import Settings
from finlongrag.core.io import write_jsonl
from finlongrag.core.schema import Chunk, Document
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.document import DocumentIndex
from finlongrag.index.faiss_store import build_faiss_embeddings
from finlongrag.ingestion.chunker import chunk_document
from finlongrag.ingestion.parser import parse_document
from finlongrag.storage.knowledge_repository import (
    IndexVersionRecord,
    IngestionTaskRecord,
    KnowledgeBaseRecord,
    KnowledgeDocumentRecord,
    create_knowledge_repository,
)


class KnowledgeService:
    """Service facade for managed knowledge bases.

    The service keeps ingestion and index building independent from FastAPI or
    CLI callers. The repository can later be replaced by PostgreSQL-backed
    storage while preserving this interface.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        repository=None,
    ) -> None:
        self.settings = settings or Settings.from_file()
        self.settings.ensure_dirs()
        self.repository = repository or create_knowledge_repository(self.settings.database_url)

    def create_knowledge_base(
        self,
        *,
        name: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeBaseRecord:
        if not name.strip():
            raise ValueError("knowledge base name is required")
        return self.repository.create_knowledge_base(name=name, description=description, metadata=metadata)

    def list_knowledge_bases(self, *, limit: int = 100, user_id: str | None = None) -> list[KnowledgeBaseRecord]:
        return self.repository.list_knowledge_bases(limit=limit, user_id=user_id)

    def get_knowledge_base(self, kb_id: str, user_id: str | None = None) -> KnowledgeBaseRecord:
        record = self.repository.get_knowledge_base(kb_id, user_id=user_id)
        if record is None:
            raise KeyError(f"knowledge base not found: {kb_id}")
        return record

    def register_local_document(
        self,
        *,
        kb_id: str,
        path: str | Path,
        domain: str = "",
        doc_id: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeDocumentRecord:
        self.get_knowledge_base(kb_id)
        resolved_path = self._resolve_local_path(path)
        if not resolved_path.exists():
            raise FileNotFoundError(f"document not found: {resolved_path}")
        if not resolved_path.is_file():
            raise ValueError(f"document path is not a file: {resolved_path}")

        inferred_doc_id = (doc_id or resolved_path.stem).strip()
        if not inferred_doc_id:
            raise ValueError("doc_id is required")
        inferred_domain = (domain or resolved_path.parent.name or "general").strip()
        inferred_title = (title or resolved_path.stem).strip()
        document_metadata = {
            "registered_from": str(path),
            "file_size": resolved_path.stat().st_size,
            **(metadata or {}),
        }
        return self.repository.register_document(
            kb_id=kb_id,
            doc_id=inferred_doc_id,
            domain=inferred_domain,
            title=inferred_title,
            path=str(resolved_path),
            source_type="local_file",
            content_hash=_sha256_file(resolved_path),
            metadata=document_metadata,
        )

    def list_documents(self, kb_id: str | None = None, *, limit: int = 500) -> list[KnowledgeDocumentRecord]:
        if kb_id:
            self.get_knowledge_base(kb_id)
        return self.repository.list_documents(kb_id, limit=limit)

    def create_ingestion_task(
        self,
        kb_id: str,
        *,
        build_index: bool = True,
        status: str = "queued",
        stage: str = "queued",
        metadata: dict[str, Any] | None = None,
    ) -> IngestionTaskRecord:
        self.get_knowledge_base(kb_id)
        documents = self.repository.list_documents(kb_id, limit=10000)
        return self.repository.create_task(
            kb_id=kb_id,
            total_documents=len(documents),
            status=status,
            stage=stage,
            metadata={"build_index": build_index, **(metadata or {})},
        )

    def ingest_knowledge_base(self, kb_id: str, *, build_index: bool = True) -> IngestionTaskRecord:
        task = self.create_ingestion_task(
            kb_id,
            build_index=build_index,
            status="running",
            stage="created",
            metadata={"execution_mode": "sync"},
        )
        return self.run_ingestion_task(task.task_id)

    def run_ingestion_task(self, task_id: str, *, raise_on_error: bool = True) -> IngestionTaskRecord:
        task = self.get_task(task_id)
        build_index = bool(task.metadata.get("build_index", True))
        documents = self.repository.list_documents(task.kb_id, limit=10000)
        task = self.repository.update_task(
            task.task_id,
            status="running",
            stage="started",
            processed_documents=0,
            total_chunks=0,
            error="",
            metadata={"build_index": build_index},
        )
        if not documents:
            return self.repository.update_task(
                task.task_id,
                status="failed",
                stage="no_documents",
                error="no documents registered for this knowledge base",
                finished=True,
            )

        processed_documents = 0
        total_chunks = 0
        current_document: KnowledgeDocumentRecord | None = None
        try:
            for document_record in documents:
                current_document = document_record
                self.repository.update_task(
                    task.task_id,
                    stage=f"parse:{document_record.doc_id}",
                    processed_documents=processed_documents,
                    total_chunks=total_chunks,
                )
                self.repository.update_document_state(document_record.document_id, status="parsing", error="")
                parsed, pages = parse_document(_document_from_record(document_record))
                chunks = _scope_chunks(
                    kb_id=task.kb_id,
                    document_id=document_record.document_id,
                    chunks=chunk_document(parsed, pages),
                )
                self.repository.replace_document_chunks(task.kb_id, document_record.document_id, chunks)
                processed_documents += 1
                total_chunks += len(chunks)
                self.repository.update_document_state(
                    document_record.document_id,
                    status="chunked",
                    page_count=len(pages),
                    chunk_count=len(chunks),
                    error="",
                    metadata={
                        "parser": parsed.metadata.get("parser", ""),
                        "page_count": len(pages),
                        "last_ingestion_task_id": task.task_id,
                    },
                )
                self.repository.update_task(
                    task.task_id,
                    stage=f"chunked:{document_record.doc_id}",
                    processed_documents=processed_documents,
                    total_chunks=total_chunks,
                )

            index_info: dict[str, Any] = {}
            if build_index:
                self.repository.update_task(
                    task.task_id,
                    stage="build_index",
                    processed_documents=processed_documents,
                    total_chunks=total_chunks,
                )
                index_info = self.build_indexes(kb_id=task.kb_id)
                for document_record in documents:
                    self.repository.update_document_state(document_record.document_id, status="indexed")

            return self.repository.update_task(
                task.task_id,
                status="succeeded",
                stage="done",
                processed_documents=processed_documents,
                total_chunks=total_chunks,
                finished=True,
                metadata={"index": index_info},
            )
        except Exception as exc:
            self.repository.update_task(
                task.task_id,
                status="failed",
                stage="failed",
                processed_documents=processed_documents,
                total_chunks=total_chunks,
                error=str(exc),
                finished=True,
            )
            if current_document is not None:
                self.repository.update_document_state(
                    current_document.document_id,
                    status="failed",
                    error=str(exc),
                )
            if raise_on_error:
                raise
            failed = self.repository.get_task(task.task_id)
            if failed is None:
                raise RuntimeError(f"failed to load failed ingestion task: {task.task_id}") from exc
            return failed

    def build_indexes(self, *, kb_id: str | None = None) -> dict[str, Any]:
        if not kb_id:
            raise ValueError("kb_id is required for managed index building")
        self.get_knowledge_base(kb_id)
        chunks = self.repository.load_chunks(kb_id=kb_id)
        if not chunks:
            raise ValueError("no chunks available for index building")

        index_version_id = uuid.uuid4().hex
        version_dir = self.settings.index_dir / "versions" / index_version_id
        chunk_index_path = version_dir / "bm25_index.pkl"
        doc_index_path = version_dir / "document_index.pkl"
        chunk_index = BM25FIndex.build(chunks, tokenizer_mode=self.settings.tokenizer_mode)
        document_index = DocumentIndex.build(chunks, tokenizer_mode=self.settings.tokenizer_mode)
        chunk_index.save(chunk_index_path)
        document_index.save(doc_index_path)
        vector_info: dict[str, Any] = {"enabled": True, **build_faiss_embeddings(self.settings, kb_id=kb_id, chunks=chunks)}
        self._publish_compatibility_indexes(chunk_index_path, doc_index_path)
        self._write_processed_snapshot(chunks)
        version = self.repository.create_index_version(
            index_version_id=index_version_id,
            kb_id=kb_id,
            tokenizer_mode=self.settings.tokenizer_mode,
            chunk_index_path=str(chunk_index_path),
            document_index_path=str(doc_index_path),
            chunk_count=len(chunks),
            document_count=len({chunk.doc_id for chunk in chunks}),
            metadata={
                "compatibility_chunk_index_path": str(self.settings.index_dir / "bm25_index.pkl"),
                "compatibility_document_index_path": str(self.settings.index_dir / "document_index.pkl"),
                "vector": vector_info,
            },
        )
        active_version = self.repository.activate_index_version(version.index_version_id)
        return {
            "kb_id": kb_id,
            "index_version_id": active_version.index_version_id,
            "status": active_version.status,
            "chunks": len(chunks),
            "documents": len({chunk.doc_id for chunk in chunks}),
            "chunk_index_path": str(chunk_index_path),
            "document_index_path": str(doc_index_path),
            "tokenizer_mode": self.settings.tokenizer_mode,
            "vector": vector_info,
        }

    def list_index_versions(self, kb_id: str | None = None, *, limit: int = 100) -> list[IndexVersionRecord]:
        if kb_id:
            self.get_knowledge_base(kb_id)
        return self.repository.list_index_versions(kb_id, limit=limit)

    def get_active_index_version(self, kb_id: str | None = None) -> IndexVersionRecord | None:
        return self.repository.get_active_index_version(kb_id=kb_id)

    def activate_index_version(self, index_version_id: str) -> IndexVersionRecord:
        version = self.repository.get_index_version(index_version_id)
        if version is None:
            raise KeyError(f"index version not found: {index_version_id}")
        chunk_index_path = Path(version.chunk_index_path)
        document_index_path = Path(version.document_index_path)
        if not chunk_index_path.exists():
            raise FileNotFoundError(f"chunk index not found: {chunk_index_path}")
        if not document_index_path.exists():
            raise FileNotFoundError(f"document index not found: {document_index_path}")
        self._publish_compatibility_indexes(chunk_index_path, document_index_path)
        return self.repository.activate_index_version(index_version_id)

    def list_tasks(self, kb_id: str | None = None, *, limit: int = 100) -> list[IngestionTaskRecord]:
        if kb_id:
            self.get_knowledge_base(kb_id)
        return self.repository.list_tasks(kb_id, limit=limit)

    def get_task(self, task_id: str) -> IngestionTaskRecord:
        record = self.repository.get_task(task_id)
        if record is None:
            raise KeyError(f"ingestion task not found: {task_id}")
        return record

    def _resolve_local_path(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.settings.project_root / candidate
        return candidate.resolve()

    def _write_processed_snapshot(self, chunks: list[Chunk]) -> None:
        documents: dict[str, Document] = {}
        for chunk in chunks:
            documents.setdefault(
                chunk.doc_id,
                Document(
                    doc_id=chunk.doc_id,
                    domain=chunk.domain,
                    title=str(chunk.metadata.get("title") or chunk.doc_id),
                    path=str(chunk.metadata.get("path") or ""),
                    metadata={
                        "kb_id": chunk.metadata.get("kb_id"),
                        "document_id": chunk.metadata.get("document_id"),
                    },
                ),
            )
        write_jsonl(self.settings.processed_dir / "documents.jsonl", documents.values())
        write_jsonl(self.settings.processed_dir / "chunks.jsonl", chunks)

    def _publish_compatibility_indexes(
        self,
        chunk_index_path: Path,
        doc_index_path: Path,
    ) -> None:
        self.settings.index_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(chunk_index_path, self.settings.index_dir / "bm25_index.pkl")
        shutil.copy2(doc_index_path, self.settings.index_dir / "document_index.pkl")


def _document_from_record(record: KnowledgeDocumentRecord) -> Document:
    return Document(
        doc_id=record.doc_id,
        domain=record.domain,
        title=record.title,
        path=record.path,
        metadata={
            "kb_id": record.kb_id,
            "document_id": record.document_id,
            "source_type": record.source_type,
            "content_hash": record.content_hash,
            **record.metadata,
        },
    )


def _scope_chunks(*, kb_id: str, document_id: str, chunks: list[Chunk]) -> list[Chunk]:
    output: list[Chunk] = []
    for chunk in chunks:
        output.append(
            replace(
                chunk,
                chunk_id=f"{kb_id}:{chunk.chunk_id}",
                metadata={
                    **chunk.metadata,
                    "kb_id": kb_id,
                    "document_id": document_id,
                    "original_chunk_id": chunk.chunk_id,
                },
            )
        )
    return output


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()
