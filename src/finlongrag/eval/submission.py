"""Contest-compatible result export."""

from __future__ import annotations

import csv
from pathlib import Path

from finlongrag.core.io import write_json, write_jsonl
from finlongrag.core.schema import AnswerResult, TokenUsage


def summarize_usage(results: list[AnswerResult]) -> TokenUsage:
    usage = TokenUsage()
    for result in results:
        usage.add(result.token_usage)
    return usage


def write_answer_csv(path: Path, results: list[AnswerResult]) -> None:
    usage = summarize_usage(results)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["qid", "answer", "prompt_tokens", "completion_tokens", "total_tokens"])
        writer.writerow(["summary", "", usage.prompt_tokens, usage.completion_tokens, usage.total_tokens])
        for result in results:
            writer.writerow(
                [
                    result.qid,
                    result.answer,
                    result.token_usage.prompt_tokens,
                    result.token_usage.completion_tokens,
                    result.token_usage.total_tokens,
                ]
            )


def write_answer_artifacts(output_dir: Path, results: list[AnswerResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_dir / "answer_results.jsonl", (result.to_dict() for result in results))
    write_answer_csv(output_dir / "answer.csv", results)
    write_json(output_dir / "evidence.json", {result.qid: [item.to_dict() for item in result.evidence] for result in results})
    write_json(output_dir / "token_usage.json", summarize_usage(results).to_dict())

