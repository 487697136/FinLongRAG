"""Run FinLongRAG API and demo UI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import uvicorn

from finlongrag.api.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve FinLongRAG API and web demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    app = create_app(dry_run=args.dry_run)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
