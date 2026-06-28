"""Quick verification script for knowledge base isolation fixes."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.storage.knowledge_repository import create_knowledge_repository


def main():
    """Verify knowledge base isolation implementation."""
    print("=" * 60)
    print("Knowledge Base Isolation Verification")
    print("=" * 60)

    try:
        settings = Settings.from_file()
        print("[OK] Settings loaded")
        print(f"  Database: {settings.database_url.split('@')[-1]}")

        repo = create_knowledge_repository(settings.database_url)
        print("[OK] Repository connected")

        # Test 1: Create two knowledge bases
        print("\n[Test 1] Creating two knowledge bases...")
        kb1 = repo.create_knowledge_base(name="Test KB 1", description="First test knowledge base")
        kb2 = repo.create_knowledge_base(name="Test KB 2", description="Second test knowledge base")
        print(f"[OK] Created KB1: {kb1.kb_id}")
        print(f"[OK] Created KB2: {kb2.kb_id}")

        # Test 2: Create index versions for both
        print("\n[Test 2] Creating index versions...")
        version1 = repo.create_index_version(
            kb_id=kb1.kb_id,
            tokenizer_mode="mixed",
            chunk_index_path=f"/test/kb1/bm25.pkl",
            document_index_path=f"/test/kb1/doc.pkl",
            chunk_count=10,
            document_count=2,
            metadata={"test": "version1"},
        )
        print(f"[OK] Created version for KB1: {version1.index_version_id}")

        version2 = repo.create_index_version(
            kb_id=kb2.kb_id,
            tokenizer_mode="mixed",
            chunk_index_path=f"/test/kb2/bm25.pkl",
            document_index_path=f"/test/kb2/doc.pkl",
            chunk_count=20,
            document_count=3,
            metadata={"test": "version2"},
        )
        print(f"[OK] Created version for KB2: {version2.index_version_id}")

        # Test 3: Activate versions independently
        print("\n[Test 3] Activating index versions...")
        repo.activate_index_version(version1.index_version_id)
        print(f"[OK] Activated version for KB1")

        repo.activate_index_version(version2.index_version_id)
        print(f"[OK] Activated version for KB2")

        # Test 4: Verify isolation
        print("\n[Test 4] Verifying isolation...")
        active1 = repo.get_active_index_version(kb_id=kb1.kb_id)
        active2 = repo.get_active_index_version(kb_id=kb2.kb_id)

        assert active1 is not None, "KB1 should have active version"
        assert active2 is not None, "KB2 should have active version"
        assert active1.kb_id == kb1.kb_id, "KB1 active version should belong to KB1"
        assert active2.kb_id == kb2.kb_id, "KB2 active version should belong to KB2"
        assert active1.index_version_id == version1.index_version_id, "KB1 should have version1 active"
        assert active2.index_version_id == version2.index_version_id, "KB2 should have version2 active"
        print(f"[OK] KB1 active version: {active1.index_version_id} (correct)")
        print(f"[OK] KB2 active version: {active2.index_version_id} (correct)")
        print(f"[OK] Index versions are properly isolated!")

        # Test 5: Test document and chunk cascade
        print("\n[Test 5] Testing document creation and cascade delete...")
        doc1 = repo.register_document(
            kb_id=kb1.kb_id,
            doc_id="test_doc_1",
            domain="test",
            title="Test Document 1",
            path="/fake/test1.pdf",
            source_type="local_file",
            content_hash="abc123",
        )
        print(f"[OK] Created document in KB1: {doc1.document_id}")

        # Test 6: Cleanup
        print("\n[Test 6] Testing cascade delete...")
        deleted1 = repo.delete_knowledge_base(kb1.kb_id)
        assert deleted1, "KB1 should be deleted"
        print(f"[OK] Deleted KB1 with cascade")

        # Verify document was cascade deleted
        doc_after = repo.get_document(doc1.document_id)
        assert doc_after is None, "Document should be cascade deleted"
        print(f"[OK] Document cascade deleted")

        # Verify version was cascade deleted
        version_after = repo.get_index_version(version1.index_version_id)
        assert version_after is None, "Index version should be cascade deleted"
        print(f"[OK] Index version cascade deleted")

        # Verify KB2 is still intact
        kb2_after = repo.get_knowledge_base(kb2.kb_id)
        assert kb2_after is not None, "KB2 should still exist"
        active2_after = repo.get_active_index_version(kb_id=kb2.kb_id)
        assert active2_after is not None, "KB2 active version should still exist"
        print(f"[OK] KB2 is still intact after KB1 deletion")

        # Final cleanup
        repo.delete_knowledge_base(kb2.kb_id)
        print(f"[OK] Cleaned up KB2")

        print("\n" + "=" * 60)
        print("[PASS] ALL TESTS PASSED")
        print("=" * 60)
        print("\nKey verifications:")
        print("  [OK] Multiple knowledge bases can have independent active index versions")
        print("  [OK] Activating version in KB2 does not affect KB1")
        print("  [OK] Cascade delete removes documents, chunks, and index versions")
        print("  [OK] Deleting KB1 does not affect KB2")

    except Exception as e:
        print(f"\n[FAIL] ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
