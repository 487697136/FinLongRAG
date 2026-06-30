"""SQLAlchemy-backed knowledge repository for PostgreSQL deployments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, or_, select, update

from finlongrag.core.schema import Chunk
from finlongrag.db import get_sync_sessionmaker
from finlongrag.db.models.knowledge import (
    IndexVersion,
    IngestionTask,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeChunkLog,
    KnowledgeDocument,
)
from finlongrag.storage.knowledge_repository import (
    IndexVersionRecord,
    IngestionTaskRecord,
    KnowledgeBaseRecord,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
)


class SQLAlchemyKnowledgeRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._sessionmaker = get_sync_sessionmaker(database_url)

    def create_knowledge_base(
        self,
        *,
        name: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> KnowledgeBaseRecord:
        now = _now()
        row = KnowledgeBase(
            kb_id=uuid.uuid4().hex,
            name=name.strip() or "默认知识库",
            description=description.strip(),
            status="active",
            metadata_json=metadata or {},
            created_by=created_by,  # 设置创建者
            created_at=now,
            updated_at=now,
        )
        with self._sessionmaker() as session:
            session.add(row)
            session.commit()
            return _kb_from_model(row)

    def list_knowledge_bases(self, *, limit: int = 100, user_id: str | None = None) -> list[KnowledgeBaseRecord]:
        with self._sessionmaker() as session:
            stmt = (
                select(KnowledgeBase)
                .where(KnowledgeBase.deleted_at.is_(None))
                .order_by(KnowledgeBase.updated_at.desc())
                .limit(limit)
            )
            # 用户隔离：只返回该用户创建的知识库（兼容旧数据 metadata.owner_id）
            if user_id:
                stmt = stmt.where(
                    or_(
                        KnowledgeBase.created_by == user_id,
                        KnowledgeBase.metadata_json["owner_id"].as_string() == user_id,
                    )
                )

            rows = session.scalars(stmt).all()
            return [_kb_from_model(row) for row in rows]

    def get_knowledge_base(self, kb_id: str, user_id: str | None = None) -> KnowledgeBaseRecord | None:
        with self._sessionmaker() as session:
            row = session.get(KnowledgeBase, kb_id)
            if row is None or row.deleted_at is not None:
                return None
            # 用户隔离：只允许访问自己创建的知识库（兼容旧数据 metadata.owner_id）
            if user_id and row.created_by != user_id:
                owner_id = (row.metadata_json or {}).get("owner_id")
                if owner_id != user_id:
                    return None
            return _kb_from_model(row)

    def delete_knowledge_base(self, kb_id: str) -> bool:
        with self._sessionmaker() as session:
            row = session.get(KnowledgeBase, kb_id)
            if row is None:
                return False

            document_ids = session.scalars(
                select(KnowledgeDocument.document_id).where(KnowledgeDocument.kb_id == kb_id)
            ).all()
            if document_ids:
                session.execute(
                    delete(KnowledgeChunkLog).where(KnowledgeChunkLog.document_id.in_(document_ids))
                )

            # Delete chunks first (foreign key constraint)
            session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.kb_id == kb_id))

            # Delete documents
            session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.kb_id == kb_id))

            # Delete ingestion tasks
            session.execute(delete(IngestionTask).where(IngestionTask.kb_id == kb_id))

            # Delete index versions
            session.execute(delete(IndexVersion).where(IndexVersion.kb_id == kb_id))

            # Finally delete the knowledge base
            session.delete(row)
            session.commit()
            return True

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
        now = _now()
        with self._sessionmaker() as session:
            kb = session.get(KnowledgeBase, kb_id)
            if kb is None:
                raise KeyError(f"knowledge base not found: {kb_id}")
            row = session.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.kb_id == kb_id,
                    KnowledgeDocument.doc_id == doc_id,
                )
            )
            if row is None:
                row = KnowledgeDocument(
                    document_id=uuid.uuid4().hex,
                    kb_id=kb_id,
                    doc_id=doc_id,
                    domain=domain,
                    title=title,
                    path=path,
                    source_type=source_type,
                    status="registered",
                    content_hash=content_hash,
                    page_count=0,
                    chunk_count=0,
                    error="",
                    metadata_json=metadata or {},
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.domain = domain
                row.title = title
                row.path = path
                row.source_type = source_type
                row.status = "registered"
                row.content_hash = content_hash
                row.error = ""
                row.metadata_json = metadata or {}
                row.updated_at = now
            kb.updated_at = now
            session.commit()
            return _document_from_model(row)

    def list_documents(self, kb_id: str | None = None, *, limit: int = 500) -> list[KnowledgeDocumentRecord]:
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.deleted_at.is_(None))
        if kb_id:
            stmt = stmt.where(KnowledgeDocument.kb_id == kb_id)
        stmt = stmt.order_by(KnowledgeDocument.updated_at.desc()).limit(limit)
        with self._sessionmaker() as session:
            return [_document_from_model(row) for row in session.scalars(stmt).all()]

    def get_document(self, document_id: str) -> KnowledgeDocumentRecord | None:
        with self._sessionmaker() as session:
            row = session.get(KnowledgeDocument, document_id)
            return _document_from_model(row) if row and row.deleted_at is None else None

    def delete_document(self, document_id: str) -> KnowledgeDocumentRecord | None:
        with self._sessionmaker() as session:
            row = session.get(KnowledgeDocument, document_id)
            if row is None:
                return None
            record = _document_from_model(row)

            session.execute(delete(KnowledgeChunkLog).where(KnowledgeChunkLog.document_id == document_id))

            # Delete all chunks belonging to this document
            session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))

            # Delete the document
            session.delete(row)

            # Update knowledge base timestamp
            kb = session.get(KnowledgeBase, row.kb_id)
            if kb is not None:
                kb.updated_at = _now()

            session.commit()
            return record

    def update_document_state(
        self,
        document_id: str,
        *,
        status: str,
        page_count: int | None = None,
        chunk_count: int | None = None,
        error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._sessionmaker() as session:
            row = session.get(KnowledgeDocument, document_id)
            if row is None:
                raise KeyError(f"document not found: {document_id}")
            row.status = status
            if page_count is not None:
                row.page_count = page_count
            if chunk_count is not None:
                row.chunk_count = chunk_count
            row.error = error
            row.updated_at = _now()
            row.metadata_json = {**dict(row.metadata_json or {}), **(metadata or {})}
            session.commit()

    def replace_document_chunks(self, kb_id: str, document_id: str, chunks: list[Chunk]) -> None:
        now = _now()
        with self._sessionmaker() as session:
            session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
            session.add_all(
                [
                    KnowledgeChunk(
                        chunk_id=chunk.chunk_id,
                        kb_id=kb_id,
                        document_id=document_id,
                        doc_id=chunk.doc_id,
                        domain=chunk.domain,
                        page=chunk.page,
                        section=chunk.section,
                        clause_id=chunk.clause_id,
                        text=chunk.text,
                        numbers=list(chunk.numbers),
                        dates=list(chunk.dates),
                        tables=list(chunk.tables),
                        metadata_json=dict(chunk.metadata),
                        created_at=now,
                    )
                    for chunk in chunks
                ]
            )
            session.commit()

    def load_chunks(self, kb_id: str | None = None) -> list[Chunk]:
        stmt = (
            select(KnowledgeChunk)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.document_id)
            .where(KnowledgeDocument.deleted_at.is_(None))
        )
        if kb_id:
            stmt = stmt.where(KnowledgeChunk.kb_id == kb_id)
        stmt = stmt.order_by(KnowledgeChunk.doc_id, KnowledgeChunk.page, KnowledgeChunk.chunk_id)
        with self._sessionmaker() as session:
            return [_chunk_from_model(row).to_chunk() for row in session.scalars(stmt).all()]

    def create_task(
        self,
        *,
        kb_id: str,
        total_documents: int,
        status: str = "running",
        stage: str = "created",
        metadata: dict[str, Any] | None = None,
    ) -> IngestionTaskRecord:
        now = _now()
        row = IngestionTask(
            task_id=uuid.uuid4().hex,
            kb_id=kb_id,
            status=status,
            stage=stage,
            total_documents=total_documents,
            processed_documents=0,
            total_chunks=0,
            error="",
            started_at=now,
            finished_at=None,
            metadata_json=metadata or {},
        )
        with self._sessionmaker() as session:
            if session.get(KnowledgeBase, kb_id) is None:
                raise KeyError(f"knowledge base not found: {kb_id}")
            session.add(row)
            session.commit()
            return _task_from_model(row)

    def update_task(
        self,
        task_id: str,
        *,
        status: str | None = None,
        stage: str | None = None,
        processed_documents: int | None = None,
        total_chunks: int | None = None,
        error: str | None = None,
        finished: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> IngestionTaskRecord:
        with self._sessionmaker() as session:
            row = session.get(IngestionTask, task_id)
            if row is None:
                raise KeyError(f"task not found: {task_id}")
            if status is not None:
                row.status = status
            if stage is not None:
                row.stage = stage
            if processed_documents is not None:
                row.processed_documents = processed_documents
            if total_chunks is not None:
                row.total_chunks = total_chunks
            if error is not None:
                row.error = error
            if finished:
                row.finished_at = _now()
            row.metadata_json = {**dict(row.metadata_json or {}), **(metadata or {})}
            session.commit()
            return _task_from_model(row)

    def get_task(self, task_id: str) -> IngestionTaskRecord | None:
        with self._sessionmaker() as session:
            row = session.get(IngestionTask, task_id)
            return _task_from_model(row) if row else None

    def list_tasks(self, kb_id: str | None = None, *, limit: int = 100) -> list[IngestionTaskRecord]:
        stmt = select(IngestionTask)
        if kb_id:
            stmt = stmt.where(IngestionTask.kb_id == kb_id)
        stmt = stmt.order_by(IngestionTask.started_at.desc()).limit(limit)
        with self._sessionmaker() as session:
            return [_task_from_model(row) for row in session.scalars(stmt).all()]

    def create_index_version(
        self,
        *,
        kb_id: str,
        tokenizer_mode: str,
        chunk_index_path: str,
        document_index_path: str,
        chunk_count: int,
        document_count: int,
        index_version_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> IndexVersionRecord:
        now = _now()
        row = IndexVersion(
            index_version_id=index_version_id or uuid.uuid4().hex,
            kb_id=kb_id,
            status="built",
            tokenizer_mode=tokenizer_mode,
            chunk_index_path=chunk_index_path,
            document_index_path=document_index_path,
            chunk_count=chunk_count,
            document_count=document_count,
            created_at=now,
            activated_at=None,
            metadata_json=metadata or {},
        )
        with self._sessionmaker() as session:
            if session.get(KnowledgeBase, kb_id) is None:
                raise KeyError(f"knowledge base not found: {kb_id}")
            session.add(row)
            session.commit()
            return _index_version_from_model(row)

    def activate_index_version(self, index_version_id: str) -> IndexVersionRecord:
        now = _now()
        with self._sessionmaker() as session:
            row = session.get(IndexVersion, index_version_id, with_for_update=True)
            if row is None:
                raise KeyError(f"index version not found: {index_version_id}")
            session.execute(
                select(IndexVersion)
                .where(IndexVersion.kb_id == row.kb_id, IndexVersion.status == "active")
                .with_for_update()
            )
            session.execute(
                update(IndexVersion)
                .where(IndexVersion.status == "active", IndexVersion.kb_id == row.kb_id)
                .values(status="superseded")
            )
            row.status = "active"
            row.activated_at = now
            kb = session.get(KnowledgeBase, row.kb_id)
            if kb is not None:
                kb.updated_at = now
            session.commit()
            return _index_version_from_model(row)

    def get_index_version(self, index_version_id: str) -> IndexVersionRecord | None:
        with self._sessionmaker() as session:
            row = session.get(IndexVersion, index_version_id)
            return _index_version_from_model(row) if row else None

    def get_active_index_version(self, kb_id: str | None = None) -> IndexVersionRecord | None:
        with self._sessionmaker() as session:
            stmt = select(IndexVersion).where(IndexVersion.status == "active")
            if kb_id:
                stmt = stmt.where(IndexVersion.kb_id == kb_id)
            stmt = stmt.order_by(IndexVersion.activated_at.desc()).limit(1)
            row = session.scalar(stmt)
            return _index_version_from_model(row) if row else None

    def list_index_versions(self, kb_id: str | None = None, *, limit: int = 100) -> list[IndexVersionRecord]:
        stmt = select(IndexVersion)
        if kb_id:
            stmt = stmt.where(IndexVersion.kb_id == kb_id)
        stmt = stmt.order_by(IndexVersion.created_at.desc()).limit(limit)
        with self._sessionmaker() as session:
            return [_index_version_from_model(row) for row in session.scalars(stmt).all()]


def _now() -> datetime:
    return datetime.now(UTC)


def _ts(value: datetime | None) -> float:
    return value.timestamp() if value else 0.0


def _kb_from_model(row: KnowledgeBase) -> KnowledgeBaseRecord:
    return KnowledgeBaseRecord(
        kb_id=row.kb_id,
        name=row.name,
        description=row.description or "",
        status=row.status,
        created_at=_ts(row.created_at),
        updated_at=_ts(row.updated_at),
        metadata=dict(row.metadata_json or {}),
    )


def _document_from_model(row: KnowledgeDocument) -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        document_id=row.document_id,
        kb_id=row.kb_id,
        doc_id=row.doc_id,
        domain=row.domain or "",
        title=row.title or "",
        path=row.path,
        source_type=row.source_type,
        status=row.status,
        content_hash=row.content_hash or "",
        page_count=row.page_count or 0,
        chunk_count=row.chunk_count or 0,
        error=row.error or "",
        created_at=_ts(row.created_at),
        updated_at=_ts(row.updated_at),
        metadata=dict(row.metadata_json or {}),
    )


def _chunk_from_model(row: KnowledgeChunk) -> KnowledgeChunkRecord:
    return KnowledgeChunkRecord(
        chunk_id=row.chunk_id,
        kb_id=row.kb_id,
        document_id=row.document_id,
        doc_id=row.doc_id,
        domain=row.domain or "",
        page=row.page,
        section=row.section or "",
        clause_id=row.clause_id or "",
        text=row.text or "",
        numbers=[str(item) for item in row.numbers or []],
        dates=[str(item) for item in row.dates or []],
        tables=[str(item) for item in row.tables or []],
        metadata=dict(row.metadata_json or {}),
        created_at=_ts(row.created_at),
    )


def _task_from_model(row: IngestionTask) -> IngestionTaskRecord:
    return IngestionTaskRecord(
        task_id=row.task_id,
        kb_id=row.kb_id,
        status=row.status,
        stage=row.stage,
        total_documents=row.total_documents or 0,
        processed_documents=row.processed_documents or 0,
        total_chunks=row.total_chunks or 0,
        error=row.error or "",
        started_at=_ts(row.started_at),
        finished_at=_ts(row.finished_at),
        metadata=dict(row.metadata_json or {}),
    )


def _index_version_from_model(row: IndexVersion) -> IndexVersionRecord:
    return IndexVersionRecord(
        index_version_id=row.index_version_id,
        kb_id=row.kb_id,
        status=row.status,
        tokenizer_mode=row.tokenizer_mode,
        chunk_index_path=row.chunk_index_path,
        document_index_path=row.document_index_path,
        chunk_count=row.chunk_count or 0,
        document_count=row.document_count or 0,
        created_at=_ts(row.created_at),
        activated_at=_ts(row.activated_at),
        metadata=dict(row.metadata_json or {}),
    )
