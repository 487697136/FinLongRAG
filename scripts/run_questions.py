"""Run dataset-style questions through FinLongRAG."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from finlongrag.core.config import Settings
from finlongrag.core.paths import DataRegistry
from finlongrag.eval.submission import write_answer_artifacts
from finlongrag.service.pipeline import FinLongRAGPipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Answer dataset questions.")
    parser.add_argument("--domains", nargs="*", default=None)
    parser.add_argument("--qids", nargs="*", default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    settings = Settings.from_file()
    registry = DataRegistry(settings)
    questions = registry.load_questions(set(args.domains) if args.domains else None)
    if args.qids:
        wanted = set(args.qids)
        questions = [question for question in questions if question.qid in wanted]
    if args.limit:
        questions = questions[: args.limit]

    pipeline = FinLongRAGPipeline(settings, dry_run=args.dry_run)
    results = []
    for index, question in enumerate(questions, start=1):
        print(f"[{index}/{len(questions)}] answering {question.qid}", flush=True)
        result = pipeline.answer(question)
        print(f"  -> {result.answer} tokens={result.token_usage.total_tokens}", flush=True)
        results.append(result)

    output_dir = args.output_dir or settings.output_dir / "runs" / "latest"
    write_answer_artifacts(output_dir, results)
    print(f"wrote artifacts -> {output_dir}", flush=True)


if __name__ == "__main__":
    main()

