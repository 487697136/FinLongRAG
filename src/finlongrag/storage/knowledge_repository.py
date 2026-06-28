"""Knowledge repository contracts and PostgreSQL factory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from finlongrag.core.schema import Chunk


@dataclass(frozen=True)
class KnowledgeBaseRecord:
    kb_id: str
    name: str
    description: str = ""
    status: str = "active"
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeDocumentRecord:
    document_id: str
    kb_id: str
    doc_id: str
    domain: str
    title: str
    path: str
    source_type: str = "local_file"
    status: str = "registered"
    content_hash: str = ""
    page_count: int = 0
    chunk_count: int = 0
    error: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeChunkRecord:
    chunk_id: str
    kb_id: str
    document_id: str
    doc_id: str
    domain: str
    page: int | None
    section: str
    clause_id: str
    text: str
    numbers: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_chunk(self) -> Chunk:
        return Chunk(
            chunk_id=self.chunk_id,
            doc_id=self.doc_id,
            domain=self.domain,
            text=self.text,
            page=self.page,
            section=self.section,
            clause_id=self.clause_id,
            numbers=list(self.numbers),
            dates=list(self.dates),
            tables=list(self.tables),
            metadata={**self.metadata, "kb_id": self.kb_id, "document_id": self.document_id},
        )


@dataclass(frozen=True)
class IngestionTaskRecord:
    task_id: str
    kb_id: str
    status: str
    stage: str
    total_documents: int = 0
    processed_documents: int = 0
    total_chunks: int = 0
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IndexVersionRecord:
    index_version_id: str
    kb_id: str
    status: str
    tokenizer_mode: str
    chunk_index_path: str
    document_index_path: str
    chunk_count: int = 0
    document_count: int = 0
    created_at: float = 0.0
    activated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KnowledgeRepository(Protocol):
    def create_knowledge_base(
        self,
        *,
        name: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> KnowledgeBaseRecord:
        ...

    def list_knowledge_bases(self, *, limit: int = 100, user_id: str | None = None) -> list[KnowledgeBaseRecord]:
        ...

    def get_knowledge_base(self, kb_id: str, user_id: str | None = None) -> KnowledgeBaseRecord | None:
        ...

    def register_document(
        self,
        *,
        kb_id: str,
        doc_id: str,
        domain: str,
        title: str,
        path: str,
        source_type: str = "local_file",
        content_hash: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeDocumentRecord:
        ...

    def list_documents(self, kb_id: str | None = None, *, limit: int = 500) -> list[KnowledgeDocumentRecord]:
        ...

    def get_document(self, document_id: str) -> KnowledgeDocumentRecord | None:
        ...

    def update_document_state(self, document_id: str, *, status: str, **kwargs) -> None:
        ...

    def replace_document_chunks(self, kb_id: str, document_id: str, chunks: list[Chunk]) -> None:
        ...

    def load_chunks(self, kb_id: str | None = None) -> list[Chunk]:
        ...

    def create_task(self, *, kb_id: str, total_documents: int, **kwargs) -> IngestionTaskRecord:
        ...

    def update_task(self, task_id: str, **kwargs) -> IngestionTaskRecord:
        ...

    def get_task(self, task_id: str) -> IngestionTaskRecord | None:
        ...

    def list_tasks(self, kb_id: str | None = None, *, limit: int = 100) -> list[IngestionTaskRecord]:
        ...

    def create_index_version(self, *, kb_id: str, tokenizer_mode: str, chunk_index_path: str, document_index_path: str, chunk_count: int, document_count: int, index_version_id: str | None = None, metadata: dict[str, Any] | None = None) -> IndexVersionRecord:
        ...

    def activate_index_version(self, index_version_id: str) -> IndexVersionRecord:
        ...

    def get_index_version(self, index_version_id: str) -> IndexVersionRecord | None:
        ...

    def get_active_index_version(self, kb_id: str | None = None) -> IndexVersionRecord | None:
        ...

    def list_index_versions(self, kb_id: str | None = None, *, limit: int = 100) -> list[IndexVersionRecord]:
        ...


def create_knowledge_repository(database_url: str) -> KnowledgeRepository:
    from finlongrag.db.session import is_postgres_url

    if not is_postgres_url(database_url):
        raise ValueError("FinLongRAG now requires PostgreSQL 18 for business data; SQLite is not supported.")
    from finlongrag.storage.sqlalchemy_knowledge_repository import SQLAlchemyKnowledgeRepository

    return SQLAlchemyKnowledgeRepository(database_url)
