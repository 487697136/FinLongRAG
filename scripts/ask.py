"""Ad-hoc grounded QA entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finlongrag.core.config import Settings
from finlongrag.service.pipeline import FinLongRAGPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask FinLongRAG an open financial question.")
    parser.add_argument("question")
    parser.add_argument("--domain", default="")
    parser.add_argument("--doc-ids", nargs="*", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = Settings.from_file()
    pipeline = FinLongRAGPipeline(settings, dry_run=args.dry_run)
    result = pipeline.ask(args.question, domain=args.domain, doc_ids=args.doc_ids or [])
    print(result.answer)
    if result.evidence:
        print("\nEvidence:")
        for item in result.evidence[:6]:
            print(f"- {item.doc_id} p{item.metadata.get('page')}: {item.evidence_text[:120]}")


if __name__ == "__main__":
    main()

