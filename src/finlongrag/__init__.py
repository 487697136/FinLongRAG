"""FinLongRAG package."""

from finlongrag.core.config import Settings

__all__ = ["Settings", "FinLongRAGPipeline", "KnowledgeService"]


def __getattr__(name: str):
    if name == "FinLongRAGPipeline":
        from finlongrag.service.pipeline import FinLongRAGPipeline

        return FinLongRAGPipeline
    if name == "KnowledgeService":
        from finlongrag.knowledge.service import KnowledgeService

        return KnowledgeService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
