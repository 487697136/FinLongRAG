"""Tests for incremental document ingestion."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from finlongrag.knowledge.service import KnowledgeService
from finlongrag.storage.knowledge_repository import KnowledgeDocumentRecord


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
