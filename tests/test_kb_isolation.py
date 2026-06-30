"""Tests for knowledge base isolation (requires PostgreSQL)."""

import os

import pytest

pytest.importorskip("psycopg")

from finlongrag.core.config import Settings
from finlongrag.storage.knowledge_repository import create_knowledge_repository


@pytest.fixture
def test_settings():
    """Create test settings with real database."""
    settings = Settings.from_file()
    return settings


@pytest.fixture
def repository(test_settings):
    """Create repository connected to test database."""
    return create_knowledge_repository(test_settings.database_url)


@pytest.mark.integration
def test_index_version_isolation(repository):
    """Test that index versions are isolated by knowledge base."""
    # Create two knowledge bases
    kb1 = repository.create_knowledge_base(name="KB1", description="Test KB 1")
    kb2 = repository.create_knowledge_base(name="KB2", description="Test KB 2")

    # Create index versions for both
    version1 = repository.create_index_version(
        kb_id=kb1.kb_id,
        tokenizer_mode="mixed",
        chunk_index_path="/fake/path1/bm25.pkl",
        document_index_path="/fake/path1/doc.pkl",
        chunk_count=10,
        document_count=2,
    )

    version2 = repository.create_index_version(
        kb_id=kb2.kb_id,
        tokenizer_mode="mixed",
        chunk_index_path="/fake/path2/bm25.pkl",
        document_index_path="/fake/path2/doc.pkl",
        chunk_count=20,
        document_count=3,
    )

    # Activate version1
    repository.activate_index_version(version1.index_version_id)

    # Check that kb1 has active version
    active1 = repository.get_active_index_version(kb_id=kb1.kb_id)
    assert active1 is not None
    assert active1.kb_id == kb1.kb_id
    assert active1.index_version_id == version1.index_version_id

    # Check that kb2 has no active version yet
    active2 = repository.get_active_index_version(kb_id=kb2.kb_id)
    assert active2 is None

    # Activate version2
    repository.activate_index_version(version2.index_version_id)

    # Check that kb2 now has active version
    active2 = repository.get_active_index_version(kb_id=kb2.kb_id)
    assert active2 is not None
    assert active2.kb_id == kb2.kb_id
    assert active2.index_version_id == version2.index_version_id

    # Check that kb1 still has its active version (not superseded)
    active1 = repository.get_active_index_version(kb_id=kb1.kb_id)
    assert active1 is not None
    assert active1.kb_id == kb1.kb_id
    assert active1.index_version_id == version1.index_version_id

    # Cleanup
    repository.delete_knowledge_base(kb1.kb_id)
    repository.delete_knowledge_base(kb2.kb_id)


@pytest.mark.integration
def test_knowledge_base_delete_cascade(repository):
    """Test that deleting a knowledge base cascades to related records."""
    # Create knowledge base
    kb = repository.create_knowledge_base(name="TestKB", description="Test")

    # Register a document
    doc = repository.register_document(
        kb_id=kb.kb_id,
        doc_id="test_doc",
        domain="test",
        title="Test Document",
        path="/fake/path.pdf",
        source_type="local_file",
        content_hash="abc123",
    )

    # Create ingestion task
    task = repository.create_task(
        kb_id=kb.kb_id,
        total_documents=1,
        status="running",
    )

    # Create index version
    version = repository.create_index_version(
        kb_id=kb.kb_id,
        tokenizer_mode="mixed",
        chunk_index_path="/fake/path/bm25.pkl",
        document_index_path="/fake/path/doc.pkl",
        chunk_count=5,
        document_count=1,
    )

    # Verify all created
    assert repository.get_knowledge_base(kb.kb_id) is not None
    assert repository.get_document(doc.document_id) is not None
    assert repository.get_task(task.task_id) is not None
    assert repository.get_index_version(version.index_version_id) is not None

    # Delete knowledge base
    deleted = repository.delete_knowledge_base(kb.kb_id)
    assert deleted is True

    # Verify cascade deletion
    assert repository.get_knowledge_base(kb.kb_id) is None
    assert repository.get_document(doc.document_id) is None
    assert repository.get_task(task.task_id) is None
    assert repository.get_index_version(version.index_version_id) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
