"""Check local FinLongRAG runtime prerequisites without mutating data."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

import faiss
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from finlongrag.core.config import Settings, get_api_key
from finlongrag.core.schema import Question, RetrievalResult
from finlongrag.db.session import get_sync_engine
from finlongrag.index.providers import create_embedding_provider
from finlongrag.retrieval.rerank import create_evidence_reranker


def main() -> int:
    parser = argparse.ArgumentParser(description="Check FinLongRAG local runtime configuration.")
    parser.add_argument("--models", action="store_true", help="Also call DashScope embedding and rerank APIs.")
    args = parser.parse_args()

    ok = True
    settings = Settings.from_file()
    print("[config] loaded")
    print(f"[config] database_url={'configured' if settings.database_url else 'missing'}")
    print(f"[config] vector_store={settings.vector_store}")
    print(f"[config] dashscope_api_key={'configured' if get_api_key() else 'missing'}")
    print(f"[faiss] version={getattr(faiss, '__version__', 'unknown')}")

    java = shutil.which("java")
    if java:
        try:
            proc = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=10, check=False)
            version_line = (proc.stderr or proc.stdout or "").splitlines()[0] if (proc.stderr or proc.stdout) else "unknown"
            print(f"[pdf] java={version_line}")
        except OSError as exc:
            ok = False
            print(f"[pdf] java_error={exc}", file=sys.stderr)
    else:
        ok = False
        print("[pdf] java=missing (required for opendataloader-pdf)", file=sys.stderr)

    try:
        import opendataloader_pdf  # noqa: F401

        print(f"[pdf] opendataloader-pdf=installed")
    except ImportError:
        ok = False
        print("[pdf] opendataloader-pdf=missing (pip install opendataloader-pdf)", file=sys.stderr)

    print(f"[pdf] hybrid_mode={settings.pdf_hybrid or 'off'}")

    try:
        engine = get_sync_engine(settings.database_url)
        with engine.connect() as conn:
            print("[postgres] connected")
            version = conn.execute(text("select version()")).scalar_one()
            print(f"[postgres] version={version.split(',')[0]}")
            tables = set(inspect(conn).get_table_names())
            required = {
                "users",
                "knowledge_bases",
                "knowledge_documents",
                "knowledge_chunks",
                "evaluation_test_sets",
                "evaluation_runs",
                "alembic_version",
            }
            missing = sorted(required - tables)
            print(f"[schema] missing={missing if missing else 'none'}")
            if missing:
                ok = False
            if "alembic_version" in tables:
                versions = [row[0] for row in conn.execute(text("select version_num from alembic_version")).fetchall()]
                print(f"[alembic] versions={versions}")
    except SQLAlchemyError as exc:
        ok = False
        print(f"[postgres] error={exc.__class__.__name__}: {exc}", file=sys.stderr)

    faiss_root = settings.index_dir / "faiss"
    print(f"[faiss] index_root={faiss_root}")
    print(f"[faiss] index_root_exists={faiss_root.exists()}")

    if args.models:
        if not get_api_key():
            print("[models] skipped: DASHSCOPE_API_KEY missing")
            ok = False
        else:
            try:
                embeddings = create_embedding_provider(settings).embed_batch(["runtime check"])
                print(f"[embedding] dimension={embeddings.shape[1] if len(embeddings) else 0}")
            except Exception as exc:
                ok = False
                print(f"[embedding] error={exc.__class__.__name__}: {exc}", file=sys.stderr)
            try:
                reranker = create_evidence_reranker(settings)
                question = Question(qid="runtime_check", question="runtime check")
                candidates = [
                    RetrievalResult(
                        chunk_id="runtime_check_chunk",
                        doc_id="runtime_check_doc",
                        domain="runtime",
                        evidence_text="FinLongRAG uses PostgreSQL, FAISS, DashScope embedding, and qwen3-rerank.",
                        score=1.0,
                        source="runtime",
                        query="runtime check",
                    )
                ]
                selected, _ = reranker.rerank(question, candidates, top_k=1)
                print(f"[rerank] selected={len(selected)}")
            except Exception as exc:
                ok = False
                print(f"[rerank] error={exc.__class__.__name__}: {exc}", file=sys.stderr)

    if ok:
        print("[result] OK")
        return 0
    print("[result] FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
