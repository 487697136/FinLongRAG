"""Parse documents referenced by questions and build chunks.jsonl."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finlongrag.core.config import Settings
from finlongrag.core.io import write_jsonl
from finlongrag.core.paths import DataRegistry
from finlongrag.ingestion.chunker import chunk_document
from finlongrag.ingestion.parser import parse_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse source documents and create FinLongRAG chunks.")
    parser.add_argument("--domains", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    settings = Settings.from_file()
    settings.ensure_dirs()
    registry = DataRegistry(settings)
    questions = registry.load_questions(set(args.domains) if args.domains else None)
    documents = registry.build_documents_for_questions(questions)
    if args.limit:
        documents = documents[: args.limit]

    parsed_docs = []
    chunks = []
    for index, document in enumerate(documents, start=1):
        print(f"[{index}/{len(documents)}] parsing {document.domain}/{document.doc_id}", flush=True)
        parsed, pages = parse_document(document, settings=settings)
        parsed_docs.append(parsed)
        chunks.extend(chunk_document(parsed, pages))

    write_jsonl(settings.processed_dir / "documents.jsonl", (document.to_dict() for document in parsed_docs))
    write_jsonl(settings.processed_dir / "chunks.jsonl", (chunk.to_dict() for chunk in chunks))
    print(f"wrote documents={len(parsed_docs)} chunks={len(chunks)} -> {settings.processed_dir}", flush=True)


if __name__ == "__main__":
    main()

