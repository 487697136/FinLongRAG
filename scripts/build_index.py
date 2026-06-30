"""Build chunk-level and document-level sparse indexes from processed chunks.jsonl.

Vector (FAISS) indexes are built by KnowledgeService.build_indexes(), not this script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finlongrag.core.config import Settings
from finlongrag.index.build import build_chunk_index, build_document_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FinLongRAG BM25F indexes.")
    parser.add_argument("--chunks", type=Path, default=None)
    parser.add_argument("--tokenizer-mode", choices=["mixed", "word", "char"], default=None)
    args = parser.parse_args()

    settings = Settings.from_file()
    settings.ensure_dirs()
    chunks_path = args.chunks or settings.processed_dir / "chunks.jsonl"
    tokenizer_mode = args.tokenizer_mode or settings.tokenizer_mode
    chunk_index = build_chunk_index(chunks_path, settings.index_dir / "bm25_index.pkl", tokenizer_mode=tokenizer_mode)
    doc_index = build_document_index(chunks_path, settings.index_dir / "document_index.pkl", tokenizer_mode=tokenizer_mode)
    print(
        f"indexed chunks={len(chunk_index.chunks)} docs={len(doc_index.index.chunks)} -> {settings.index_dir}",
        flush=True,
    )
    if settings.enable_vector_retrieval:
        print(
            "Note: FAISS vector indexes are built via KnowledgeService.build_indexes() after document ingestion.",
            flush=True,
        )


if __name__ == "__main__":
    main()
