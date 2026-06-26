"""Execution trace schema (Phase 7 nested-span persistence target).

Mirrors the existing JSONL trace events written by `framework/trace.py`.
`TraceRun` is one pipeline invocation (e.g. one `ask()` call); `TraceNode` is
one span within it, self-referential via `parent_node_id` so nested stages
(retrieve -> rerank -> verify) round-trip without a separate adjacency table.
JSONL stays as an optional dev-mode mirror — this table is additive, not a
replacement, until Phase 7 actually wires the writer.
"""

from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from finlongrag.db.base import Base, JSONVariant, new_id


class TraceRun(Base):
    __tablename__ = "trace_runs"

    run_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32), default="ask")
    status: Mapped[str] = mapped_column(String(32), default="running")
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_json: Mapped[dict] = mapped_column("input", JSONVariant, default=dict)
    output_json: Mapped[dict] = mapped_column("output", JSONVariant, default=dict)
    error: Mapped[str | None] = mapped_column(String(2000), nullable=True)


class TraceNode(Base):
    __tablename__ = "trace_nodes"

    node_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("trace_runs.run_id"), index=True)
    parent_node_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("trace_nodes.node_id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120))
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_json: Mapped[dict] = mapped_column("input", JSONVariant, default=dict)
    output_json: Mapped[dict] = mapped_column("output", JSONVariant, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONVariant, default=dict)
