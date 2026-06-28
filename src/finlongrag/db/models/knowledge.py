"""Knowledge base / document / chunk / ingestion / index-version schema.

Two identifiers matter for documents: `doc_id` is the logical/business document
identity threaded through `Chunk.doc_id`, retrieval, and citations; `document_id`
is a surrogate key for one registration of a `doc_id` into one `kb_id`.
Chunk embeddings are stored in the local FAISS index under `data/index/faiss`.
"""

from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from finlongrag.db.base import Base, JSONVariant, TimestampMixin, new_id


class KnowledgeBase(Base, TimestampMixin):
    __tablename__ = "knowledge_bases"

    kb_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONVariant, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("kb_id", "doc_id", name="uq_knowledge_documents_kb_doc"),)

    document_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kb_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_bases.kb_id"), index=True)
    doc_id: Mapped[str] = mapped_column(String(128), index=True)
    domain: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(500), default="")
    path: Mapped[str] = mapped_column(String(1000), default="")
    source_type: Mapped[str] = mapped_column(String(32), default="local_file")
    status: Mapped[str] = mapped_column(String(32), default="registered")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(2000), default="")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONVariant, default=dict)
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    chunk_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_bases.kb_id"), index=True)
    document_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("knowledge_documents.document_id"), index=True
    )
    doc_id: Mapped[str] = mapped_column(String(128), index=True)
    domain: Mapped[str] = mapped_column(String(64), default="")
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str] = mapped_column(String(500), default="")
    clause_id: Mapped[str] = mapped_column(String(200), default="")
    text: Mapped[str] = mapped_column(String, default="")
    numbers: Mapped[list] = mapped_column(JSONVariant, default=list)
    dates: Mapped[list] = mapped_column(JSONVariant, default=list)
    tables: Mapped[list] = mapped_column(JSONVariant, default=list)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONVariant, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default="now()")


class KnowledgeChunkLog(Base):
    """Per-stage ETL timing/observability. Not used by any current code path -
    Phase 6 (node-based ingestion pipeline) is the first writer."""

    __tablename__ = "knowledge_chunk_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("knowledge_documents.document_id"), index=True
    )
    stage: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class IngestionTask(Base):
    __tablename__ = "ingestion_tasks"

    task_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    kb_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_bases.kb_id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    stage: Mapped[str] = mapped_column(String(128), default="created")
    total_documents: Mapped[int] = mapped_column(Integer, default=0)
    processed_documents: Mapped[int] = mapped_column(Integer, default=0)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(String(2000), default="")
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default="now()")
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONVariant, default=dict)


class IndexVersion(Base):
    __tablename__ = "index_versions"

    index_version_id: Mapped[str] = mapped_column(String(64), primary_key=True, default=new_id)
    kb_id: Mapped[str] = mapped_column(String(64), ForeignKey("knowledge_bases.kb_id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="built")
    tokenizer_mode: Mapped[str] = mapped_column(String(32), default="mixed")
    chunk_index_path: Mapped[str] = mapped_column(String(1000), default="")
    document_index_path: Mapped[str] = mapped_column(String(1000), default="")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default="now()")
    activated_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONVariant, default=dict)
