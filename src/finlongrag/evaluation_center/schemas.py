"""Evaluation center schemas."""

from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class RetrievalStrategy(str, enum.Enum):
    bm25 = "bm25"
    vector = "vector"
    hybrid = "hybrid"


class EvalConfig(BaseModel):
    kb_id: str
    test_set_id: str
    strategy: RetrievalStrategy = RetrievalStrategy.hybrid
    top_k: int = Field(default=8, ge=1, le=50)


class TestSetItem(BaseModel):
    question: str
    answer: str = ""
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestSet(BaseModel):
    id: str
    name: str
    description: str = ""
    sheet_names: list[str] = Field(default_factory=list)
    items: list[TestSetItem] = Field(default_factory=list)
    file_name: str = ""
    count: int = 0
    created_at: str = ""


class EvalItemResult(BaseModel):
    question: str
    expected_source: str = ""
    expected_answer: str = ""
    hit: bool = False
    rank: int = 0
    matched_chunk: str = ""
    score: float = 0.0
    sources: list[dict[str, Any]] = Field(default_factory=list)


class EvalMetrics(BaseModel):
    total: int = 0
    hit_count: int = 0
    recall: float = 0.0
    mrr: float = 0.0


class EvalReport(BaseModel):
    id: str
    kb_id: str
    kb_name: str = ""
    test_set_id: str
    test_set_name: str = ""
    strategy: str
    top_k: int
    status: str = "running"
    metrics: EvalMetrics = Field(default_factory=EvalMetrics)
    details: list[EvalItemResult] = Field(default_factory=list)
    error_message: str = ""
    progress_current: int = 0
    progress_total: int = 0
    created_at: str = ""
    finished_at: str = ""

