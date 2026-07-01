"""Configuration loading for FinLongRAG."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=True)
except Exception:
    pass


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _nested(data: dict[str, Any], path: str, default: Any) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_required(name: str) -> str:
    value = os.getenv(name)
    if value in (None, ""):
        raise RuntimeError(f"{name} is required. Copy .env.example to .env and set it for your PostgreSQL database.")
    return value


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    config_path: Path = PROJECT_ROOT / "config" / "finlongrag.yaml"
    dataset_root: Path = PROJECT_ROOT / "data" / "raw_dataset"
    raw_root: Path = PROJECT_ROOT / "data" / "raw_dataset" / "raw"
    questions_root: Path = PROJECT_ROOT / "data" / "raw_dataset" / "questions" / "group_a"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    index_dir: Path = PROJECT_ROOT / "data" / "index"
    output_dir: Path = PROJECT_ROOT / "output"
    database_url: str = ""
    object_storage_root: Path = PROJECT_ROOT / "data" / "object_storage"
    qwen_model: str = "qwen-plus"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    request_timeout_seconds: int = 120
    max_retries: int = 2
    temperature: float = 0.0
    answer_max_tokens: int = 768
    tokenizer_mode: str = "mixed"
    top_k_per_query: int = 24
    fused_top_k: int = 40
    evidence_top_k: int = 8
    max_evidence_chars: int = 12000
    evidence_per_claim: int = 4
    evidence_chars_per_claim: int = 3200
    parent_window_chars: int = 900
    blind_top_docs: int = 8
    scoring_mode: str = "bm25f"
    enable_vector_retrieval: bool = True
    vector_embedding_provider: str = "dashscope"
    vector_embedding_model: str = "text-embedding-v4"
    vector_dimension: int = 1024
    vector_batch_size: int = 10
    vector_embedding_concurrency: int = 2
    vector_store: str = "faiss"
    bm25_channel_weight: float = 1.0
    vector_channel_weight: float = 0.45
    rerank_provider: str = "dashscope"
    rerank_model: str = "qwen3-rerank"
    rerank_base_url: str = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    rerank_top_k_multiplier: int = 4
    pdf_hybrid: str = "off"
    pdf_hybrid_url: str = ""
    enable_legacy_api: bool = False
    conditional_rerank_enabled: bool = True
    rerank_trigger_threshold: float = 0.15
    query_cache_enabled: bool = True
    query_cache_max_entries: int = 256
    query_cache_ttl_seconds: int = 3600
    require_kb_scope_for_rag: bool = True
    upload_max_bytes: int = 100 * 1024 * 1024
    upload_allowed_extensions: tuple[str, ...] = (".pdf", ".txt", ".md", ".docx", ".xlsx", ".csv", ".json", ".jsonl")
    cors_origins: tuple[str, ...] = ("*",)

    @classmethod
    def from_file(cls, path: Path | None = None) -> Settings:
        config_path = (path or cls.config_path).resolve()
        data = _read_yaml(config_path)
        project_root = cls.project_root
        paths = data.get("paths") or {}
        processed_default = project_root / str(paths.get("processed_dir", "data/processed"))
        index_default = project_root / str(paths.get("index_dir", "data/index"))
        output_default = project_root / str(paths.get("output_dir", "output"))
        configured_database_url = _env_required("FINLONGRAG_DATABASE_URL")
        object_storage_default = project_root / str(paths.get("object_storage_root", "data/object_storage"))
        return cls(
            config_path=config_path,
            dataset_root=_env_path("FINLONGRAG_DATASET_ROOT", cls.dataset_root),
            raw_root=_env_path("FINLONGRAG_RAW_ROOT", cls.raw_root),
            questions_root=_env_path("FINLONGRAG_QUESTIONS_ROOT", cls.questions_root),
            processed_dir=_env_path("FINLONGRAG_PROCESSED_DIR", processed_default),
            index_dir=_env_path("FINLONGRAG_INDEX_DIR", index_default),
            output_dir=_env_path("FINLONGRAG_OUTPUT_DIR", output_default),
            database_url=configured_database_url,
            object_storage_root=_env_path("FINLONGRAG_OBJECT_STORAGE_ROOT", object_storage_default),
            qwen_model=_env("FINLONGRAG_QWEN_MODEL", str(_nested(data, "model.name", cls.qwen_model))),
            qwen_base_url=_env("FINLONGRAG_QWEN_BASE_URL", str(_nested(data, "model.base_url", cls.qwen_base_url))),
            request_timeout_seconds=int(_nested(data, "model.request_timeout_seconds", cls.request_timeout_seconds)),
            max_retries=int(_nested(data, "model.max_retries", cls.max_retries)),
            temperature=float(_nested(data, "model.temperature", cls.temperature)),
            answer_max_tokens=int(_nested(data, "model.answer_max_tokens", cls.answer_max_tokens)),
            tokenizer_mode=str(_nested(data, "retrieval.tokenizer_mode", cls.tokenizer_mode)),
            top_k_per_query=int(_nested(data, "retrieval.top_k_per_query", cls.top_k_per_query)),
            fused_top_k=int(_nested(data, "retrieval.fused_top_k", cls.fused_top_k)),
            evidence_top_k=int(_nested(data, "retrieval.evidence_top_k", cls.evidence_top_k)),
            max_evidence_chars=int(_nested(data, "retrieval.max_evidence_chars", cls.max_evidence_chars)),
            evidence_per_claim=int(_nested(data, "reasoning.evidence_per_claim", cls.evidence_per_claim)),
            evidence_chars_per_claim=int(
                _nested(data, "reasoning.evidence_chars_per_claim", cls.evidence_chars_per_claim)
            ),
            parent_window_chars=int(_nested(data, "reasoning.parent_window_chars", cls.parent_window_chars)),
            blind_top_docs=int(_nested(data, "retrieval.blind_top_docs", cls.blind_top_docs)),
            scoring_mode=str(_nested(data, "retrieval.scoring_mode", cls.scoring_mode)),
            enable_vector_retrieval=_env_bool(
                "FINLONGRAG_ENABLE_VECTOR_RETRIEVAL",
                bool(_nested(data, "retrieval.enable_vector_retrieval", cls.enable_vector_retrieval)),
            ),
            vector_embedding_provider=_env(
                "FINLONGRAG_VECTOR_EMBEDDING_PROVIDER",
                str(_nested(data, "retrieval.vector_embedding_provider", cls.vector_embedding_provider)),
            ),
            vector_embedding_model=_env(
                "FINLONGRAG_VECTOR_EMBEDDING_MODEL",
                str(_nested(data, "retrieval.vector_embedding_model", cls.vector_embedding_model)),
            ),
            vector_dimension=int(
                _env("FINLONGRAG_VECTOR_DIMENSION", str(_nested(data, "retrieval.vector_dimension", cls.vector_dimension)))
            ),
            vector_batch_size=int(
                _env(
                    "FINLONGRAG_VECTOR_BATCH_SIZE",
                    str(_nested(data, "retrieval.vector_batch_size", cls.vector_batch_size)),
                )
            ),
            vector_embedding_concurrency=int(
                _env(
                    "FINLONGRAG_VECTOR_EMBEDDING_CONCURRENCY",
                    str(_nested(data, "retrieval.vector_embedding_concurrency", cls.vector_embedding_concurrency)),
                )
            ),
            vector_store=_env("FINLONGRAG_VECTOR_STORE", str(_nested(data, "retrieval.vector_store", cls.vector_store))),
            bm25_channel_weight=float(
                _env(
                    "FINLONGRAG_BM25_CHANNEL_WEIGHT",
                    str(_nested(data, "retrieval.bm25_channel_weight", cls.bm25_channel_weight)),
                )
            ),
            vector_channel_weight=float(
                _env(
                    "FINLONGRAG_VECTOR_CHANNEL_WEIGHT",
                    str(_nested(data, "retrieval.vector_channel_weight", cls.vector_channel_weight)),
                )
            ),
            rerank_provider=_env("FINLONGRAG_RERANK_PROVIDER", str(_nested(data, "rerank.provider", cls.rerank_provider))),
            rerank_model=_env("FINLONGRAG_RERANK_MODEL", str(_nested(data, "rerank.model", cls.rerank_model))),
            rerank_base_url=_env(
                "FINLONGRAG_RERANK_BASE_URL", str(_nested(data, "rerank.base_url", cls.rerank_base_url))
            ),
            rerank_top_k_multiplier=int(
                _env(
                    "FINLONGRAG_RERANK_TOP_K_MULTIPLIER",
                    str(_nested(data, "rerank.top_k_multiplier", cls.rerank_top_k_multiplier)),
                )
            ),
            pdf_hybrid=_env(
                "FINLONGRAG_PDF_HYBRID",
                str(_nested(data, "ingestion.pdf_hybrid", cls.pdf_hybrid)),
            ),
            pdf_hybrid_url=_env(
                "FINLONGRAG_PDF_HYBRID_URL",
                str(_nested(data, "ingestion.pdf_hybrid_url", cls.pdf_hybrid_url)),
            ),
            enable_legacy_api=_env_bool("FINLONGRAG_ENABLE_LEGACY_API", cls.enable_legacy_api),
            conditional_rerank_enabled=_env_bool(
                "FINLONGRAG_CONDITIONAL_RERANK",
                bool(_nested(data, "agent.conditional_rerank_enabled", cls.conditional_rerank_enabled)),
            ),
            rerank_trigger_threshold=float(
                _env(
                    "FINLONGRAG_RERANK_TRIGGER_THRESHOLD",
                    str(_nested(data, "agent.rerank_trigger_threshold", cls.rerank_trigger_threshold)),
                )
            ),
            query_cache_enabled=_env_bool(
                "FINLONGRAG_QUERY_CACHE_ENABLED",
                bool(_nested(data, "agent.query_cache_enabled", cls.query_cache_enabled)),
            ),
            query_cache_max_entries=int(
                _env(
                    "FINLONGRAG_QUERY_CACHE_MAX_ENTRIES",
                    str(_nested(data, "agent.query_cache_max_entries", cls.query_cache_max_entries)),
                )
            ),
            query_cache_ttl_seconds=int(
                _env(
                    "FINLONGRAG_QUERY_CACHE_TTL_SECONDS",
                    str(_nested(data, "agent.query_cache_ttl_seconds", cls.query_cache_ttl_seconds)),
                )
            ),
            require_kb_scope_for_rag=_env_bool(
                "FINLONGRAG_REQUIRE_KB_SCOPE",
                bool(_nested(data, "agent.require_kb_scope_for_rag", cls.require_kb_scope_for_rag)),
            ),
            upload_max_bytes=int(
                _env(
                    "FINLONGRAG_UPLOAD_MAX_BYTES",
                    str(_nested(data, "api.upload_max_bytes", cls.upload_max_bytes)),
                )
            ),
            upload_allowed_extensions=tuple(
                str(item).lower()
                for item in _nested(
                    data,
                    "api.upload_allowed_extensions",
                    list(cls.upload_allowed_extensions),
                )
            ),
            cors_origins=tuple(
                str(item).strip()
                for item in _env("FINLONGRAG_CORS_ORIGINS", ",".join(cls.cors_origins)).split(",")
                if str(item).strip()
            ) or cls.cors_origins,
        )

    def ensure_dirs(self) -> None:
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.object_storage_root.mkdir(parents=True, exist_ok=True)


def get_api_key() -> str | None:
    from finlongrag.core.api_key_context import get_request_api_key

    scoped = get_request_api_key()
    if scoped:
        return scoped
    return (
        os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("BAILIAN_API_KEY")
        or os.getenv("QWEN_API_KEY")
        or os.getenv("OPENAI_API_KEY")
    )
