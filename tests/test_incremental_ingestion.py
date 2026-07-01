"""Tests for incremental document ingestion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from finlongrag.knowledge.service import KnowledgeService
from finlongrag.storage.knowledge_repository import IngestionTaskRecord, KnowledgeDocumentRecord
from finlongrag.storage.sqlalchemy_knowledge_repository import _normalize_task_stage


def _doc(*, document_id: str, status: str = "indexed", content_hash: str = "abc") -> KnowledgeDocumentRecord:
    return KnowledgeDocumentRecord(
        document_id=document_id,
        kb_id="kb1",
        doc_id=f"doc-{document_id}",
        domain="general",
        title="demo",
        path="uploads/kb1/demo.pdf",
        status=status,
        content_hash=content_hash,
    )


def test_document_needs_ingestion_skips_unchanged_indexed_doc(tmp_path: Path):
    service = KnowledgeService(
        settings=MagicMock(object_storage_root=tmp_path, project_root=tmp_path),
        repository=MagicMock(),
    )
    record = _doc(document_id="d1", status="indexed", content_hash="deadbeef")

    pdf_path = tmp_path / "uploads" / "kb1" / "demo.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"same-content")

    with patch("finlongrag.knowledge.service._sha256_file", return_value="deadbeef"):
        assert service._document_needs_ingestion(record) is False


def test_document_needs_ingestion_detects_changed_file(tmp_path: Path):
    service = KnowledgeService(
        settings=MagicMock(object_storage_root=tmp_path, project_root=tmp_path),
        repository=MagicMock(),
    )
    record = _doc(document_id="d1", status="indexed", content_hash="old-hash")

    pdf_path = tmp_path / "uploads" / "kb1" / "demo.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"changed-content")

    with patch("finlongrag.knowledge.service._sha256_file", return_value="new-hash"):
        assert service._document_needs_ingestion(record) is True


def test_document_needs_ingestion_for_new_registered_doc(tmp_path: Path):
    service = KnowledgeService(
        settings=MagicMock(object_storage_root=tmp_path, project_root=tmp_path),
        repository=MagicMock(),
    )
    record = _doc(document_id="d1", status="registered", content_hash="")
    assert service._document_needs_ingestion(record) is True


def test_ingestion_task_stage_keeps_document_id_in_metadata(tmp_path: Path):
    repository = MagicMock()
    document = _doc(document_id="5e913a73b6c64f5f97d6f9f9923f578d_2", status="indexed", content_hash="deadbeef")
    task = IngestionTaskRecord(
        task_id="task1",
        kb_id="kb1",
        status="queued",
        stage="queued",
        total_documents=1,
        metadata={"build_index": False, "force": False},
    )
    repository.get_task.return_value = task
    repository.list_documents.return_value = [document]
    repository.get_active_index_version.return_value = object()
    repository.update_task.side_effect = lambda task_id, **kwargs: IngestionTaskRecord(
        task_id=task_id,
        kb_id="kb1",
        status=kwargs.get("status", "running"),
        stage=kwargs.get("stage", "running"),
        processed_documents=kwargs.get("processed_documents", 0),
        total_chunks=kwargs.get("total_chunks", 0),
        metadata=kwargs.get("metadata", {}),
    )
    service = KnowledgeService(
        settings=MagicMock(object_storage_root=tmp_path, project_root=tmp_path),
        repository=repository,
    )

    with patch.object(service, "_document_needs_ingestion", side_effect=[True, False]):
        service.run_ingestion_task("task1")

    skip_call = next(
        call for call in repository.update_task.call_args_list
        if call.kwargs.get("stage") == "skip_unchanged"
    )
    assert len(skip_call.kwargs["stage"]) <= 32
    assert skip_call.kwargs["metadata"]["current_document_id"] == document.document_id
    assert skip_call.kwargs["metadata"]["current_doc_id"] == document.doc_id


def test_sqlalchemy_repository_normalizes_legacy_task_stage_length():
    normalized = _normalize_task_stage("parse:5e913a73b6c64f5f97d6f9f9923f578d_2")

    assert len(normalized) == 32
    assert normalized.startswith("parse:")


def test_build_indexes_uses_incremental_vector_for_force_retry_without_reprocess(tmp_path: Path):
    repository = MagicMock()
    service = KnowledgeService(
        settings=MagicMock(
            object_storage_root=tmp_path,
            project_root=tmp_path,
            index_dir=tmp_path / "index",
            processed_dir=tmp_path / "processed",
            tokenizer_mode="mixed",
            enable_vector_retrieval=True,
        ),
        repository=repository,
    )
    repository.load_chunks.return_value = [MagicMock(doc_id="doc-1", metadata={"document_id": "d1"})]

    with patch.object(service, "get_knowledge_base", return_value=object()), patch(
        "finlongrag.knowledge.service.BM25FIndex"
    ) as bm25_cls, patch("finlongrag.knowledge.service.DocumentIndex") as doc_cls, patch(
        "finlongrag.knowledge.service.faiss_index_exists",
        return_value=True,
    ), patch(
        "finlongrag.knowledge.service.append_faiss_embeddings",
        return_value={"appended": 1},
    ) as append_vectors, patch(
        "finlongrag.knowledge.service.build_faiss_embeddings"
    ) as build_vectors, patch.object(service, "_publish_compatibility_indexes"), patch.object(
        service, "_write_processed_snapshot"
    ), patch.object(
        service.repository,
        "create_index_version",
        return_value=MagicMock(index_version_id="v1"),
    ), patch.object(
        service.repository,
        "activate_index_version",
        return_value=MagicMock(index_version_id="v1", status="active"),
    ), patch(
        "finlongrag.knowledge.service.merge_global_indexes",
        return_value={},
    ):
        bm25_cls.build.return_value = MagicMock()
        doc_cls.build.return_value = MagicMock()
        service.build_indexes(
            kb_id="kb1",
            incremental_document_ids=["d1"],
            force_vector_rebuild=False,
        )

    append_vectors.assert_called_once()
    build_vectors.assert_not_called()
