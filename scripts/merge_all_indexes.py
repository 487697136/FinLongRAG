"""Merge all knowledge base indexes into a global index for multi-KB support."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finlongrag.core.config import Settings
from finlongrag.storage.knowledge_repository import create_knowledge_repository
from finlongrag.index.bm25 import BM25FIndex
from finlongrag.index.document import DocumentIndex


def main():
    """Merge all KB indexes into a global index."""
    print("=" * 60)
    print("Merging All Knowledge Base Indexes")
    print("=" * 60)

    settings = Settings.from_file()
    repo = create_knowledge_repository(settings.database_url)

    # Get all knowledge bases
    kbs = repo.list_knowledge_bases()
    print(f"\nFound {len(kbs)} knowledge bases")

    # Collect all chunks from all KBs
    all_chunks = []
    for kb in kbs:
        print(f"\nKB: {kb.name} (ID: {kb.kb_id})")
        chunks = repo.load_chunks(kb_id=kb.kb_id)
        print(f"  Loaded {len(chunks)} chunks")
        all_chunks.extend(chunks)

    print(f"\n[Total] {len(all_chunks)} chunks from all KBs")

    # Build global BM25 index
    print("\nBuilding global BM25 index...")
    global_index = BM25FIndex.build(all_chunks, tokenizer_mode=settings.tokenizer_mode)

    # Save to global location
    global_index_path = settings.index_dir / "bm25_index_global.pkl"
    global_index.save(global_index_path)
    print(f"[OK] Saved global BM25 index to: {global_index_path}")

    # Build global document index
    print("\nBuilding global document index...")
    global_doc_index = DocumentIndex.build(all_chunks, tokenizer_mode=settings.tokenizer_mode)
    global_doc_index_path = settings.index_dir / "document_index_global.pkl"
    global_doc_index.save(global_doc_index_path)
    print(f"[OK] Saved global document index to: {global_doc_index_path}")

    print("\n" + "=" * 60)
    print("[SUCCESS] Global indexes created!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Update Pipeline to load global indexes")
    print("2. Restart the service")


if __name__ == "__main__":
    main()
