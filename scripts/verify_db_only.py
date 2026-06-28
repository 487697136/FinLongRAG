"""Simplified verification - database layer only."""

import os
import sys
from datetime import UTC, datetime

# Test database connection and isolation features
def test_database_isolation():
    """Test knowledge base isolation at database level."""

    # Set up database connection
    database_url = os.getenv("FINLONGRAG_DATABASE_URL", "postgresql://finlongrag:123456@localhost:5432/finlongrag")

    print("=" * 60)
    print("Database Layer Isolation Test")
    print("=" * 60)
    print(f"Database: {database_url.split('@')[-1]}")

    try:
        # Import only what we need
        import uuid
        from sqlalchemy import create_engine, select, update, delete
        from sqlalchemy.orm import sessionmaker

        # Import models
        sys.path.insert(0, 'src')
        from finlongrag.db.models.knowledge import KnowledgeBase, IndexVersion

        engine = create_engine(database_url)
        SessionLocal = sessionmaker(bind=engine)

        print("✓ Database connection established")

        with SessionLocal() as session:
            # Clean up any test data first
            session.execute(delete(IndexVersion).where(IndexVersion.kb_id.like('test_kb_%')))
            session.execute(delete(KnowledgeBase).where(KnowledgeBase.kb_id.like('test_kb_%')))
            session.commit()
            print("✓ Cleaned up test data")

            # Test 1: Create two knowledge bases
            print("\n[Test 1] Creating two knowledge bases...")
            kb1_id = f"test_kb_{uuid.uuid4().hex[:8]}"
            kb2_id = f"test_kb_{uuid.uuid4().hex[:8]}"
            now = datetime.now(UTC)

            kb1 = KnowledgeBase(
                kb_id=kb1_id,
                name="Test KB 1",
                description="First test",
                status="active",
                metadata_json={},
                created_at=now,
                updated_at=now,
            )
            kb2 = KnowledgeBase(
                kb_id=kb2_id,
                name="Test KB 2",
                description="Second test",
                status="active",
                metadata_json={},
                created_at=now,
                updated_at=now,
            )
            session.add_all([kb1, kb2])
            session.commit()
            print(f"✓ Created KB1: {kb1_id}")
            print(f"✓ Created KB2: {kb2_id}")

            # Test 2: Create index versions
            print("\n[Test 2] Creating index versions...")
            v1_id = uuid.uuid4().hex
            v2_id = uuid.uuid4().hex

            version1 = IndexVersion(
                index_version_id=v1_id,
                kb_id=kb1_id,
                status="built",
                tokenizer_mode="mixed",
                chunk_index_path="/test/v1/bm25.pkl",
                document_index_path="/test/v1/doc.pkl",
                chunk_count=10,
                document_count=2,
                created_at=now,
                metadata_json={},
            )
            version2 = IndexVersion(
                index_version_id=v2_id,
                kb_id=kb2_id,
                status="built",
                tokenizer_mode="mixed",
                chunk_index_path="/test/v2/bm25.pkl",
                document_index_path="/test/v2/doc.pkl",
                chunk_count=20,
                document_count=3,
                created_at=now,
                metadata_json={},
            )
            session.add_all([version1, version2])
            session.commit()
            print(f"✓ Created version1 for KB1")
            print(f"✓ Created version2 for KB2")

            # Test 3: Activate version1 (only for KB1)
            print("\n[Test 3] Activating versions independently...")

            # Activate version1
            session.execute(
                update(IndexVersion)
                .where(IndexVersion.status == "active", IndexVersion.kb_id == kb1_id)
                .values(status="superseded")
            )
            version1.status = "active"
            version1.activated_at = now
            session.commit()
            print(f"✓ Activated version1 for KB1")

            # Activate version2
            session.execute(
                update(IndexVersion)
                .where(IndexVersion.status == "active", IndexVersion.kb_id == kb2_id)
                .values(status="superseded")
            )
            version2.status = "active"
            version2.activated_at = now
            session.commit()
            print(f"✓ Activated version2 for KB2")

            # Test 4: Verify isolation
            print("\n[Test 4] Verifying isolation...")

            # Check KB1 active version
            active1 = session.scalar(
                select(IndexVersion)
                .where(IndexVersion.status == "active", IndexVersion.kb_id == kb1_id)
                .order_by(IndexVersion.activated_at.desc())
                .limit(1)
            )

            # Check KB2 active version
            active2 = session.scalar(
                select(IndexVersion)
                .where(IndexVersion.status == "active", IndexVersion.kb_id == kb2_id)
                .order_by(IndexVersion.activated_at.desc())
                .limit(1)
            )

            assert active1 is not None, "KB1 should have active version"
            assert active2 is not None, "KB2 should have active version"
            assert active1.index_version_id == v1_id, "KB1 active should be version1"
            assert active2.index_version_id == v2_id, "KB2 active should be version2"

            print(f"✓ KB1 active: {active1.index_version_id[:8]}... (correct)")
            print(f"✓ KB2 active: {active2.index_version_id[:8]}... (correct)")
            print(f"✓ Index versions are properly isolated!")

            # Test 5: Cleanup
            print("\n[Test 5] Cleanup...")
            session.delete(version1)
            session.delete(version2)
            session.delete(kb1)
            session.delete(kb2)
            session.commit()
            print(f"✓ Cleaned up test data")

        print("\n" + "=" * 60)
        print("✅ ALL DATABASE TESTS PASSED")
        print("=" * 60)
        print("\nKey verifications:")
        print("  ✓ Multiple KBs can have independent active index versions")
        print("  ✓ Activating version in KB2 does not affect KB1")
        print("  ✓ Database isolation logic works correctly")

        return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_database_isolation()
    sys.exit(0 if success else 1)
