"""Lightweight trace recorder for pipeline observability."""

from __future__ import annotations

import contextvars
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from finlongrag.core.io import append_jsonl

_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_NODE_STACK: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar("node_stack", default=())


@dataclass
class TraceNode:
    trace_id: str
    node_id: str
    parent_node_id: str | None
    depth: int
    node_name: str
    node_type: str
    status: str
    start_time: float
    end_time: float | None = None
    duration_ms: float | None = None
    error_message: str | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceRun:
    trace_id: str
    trace_name: str
    status: str
    start_time: float
    end_time: float | None = None
    duration_ms: float | None = None
    error_message: str | None = None
    extra_data: dict[str, Any] = field(default_factory=dict)
    nodes: list[TraceNode] = field(default_factory=list)


class TraceRecorder:
    def __init__(self, jsonl_path: Path | None = None) -> None:
        self.jsonl_path = jsonl_path
        self.runs: dict[str, TraceRun] = {}

    def start_run(self, trace_name: str, extra_data: dict[str, Any] | None = None) -> TraceRun:
        trace_id = uuid.uuid4().hex
        run = TraceRun(trace_id=trace_id, trace_name=trace_name, status="RUNNING", start_time=time.time())
        run.extra_data.update(extra_data or {})
        self.runs[trace_id] = run
        _TRACE_ID.set(trace_id)
        _NODE_STACK.set(())
        return run

    def finish_run(self, trace_id: str, status: str = "SUCCESS", error: str | None = None) -> None:
        run = self.runs.get(trace_id)
        if run is None:
            return
        run.status = status
        run.error_message = error
        run.end_time = time.time()
        run.duration_ms = (run.end_time - run.start_time) * 1000
        if self.jsonl_path:
            append_jsonl(self.jsonl_path, asdict(run))

    def start_node(self, name: str, node_type: str, extra_data: dict[str, Any] | None = None) -> TraceNode | None:
        trace_id = _TRACE_ID.get()
        if not trace_id:
            return None
        stack = _NODE_STACK.get()
        node = TraceNode(
            trace_id=trace_id,
            node_id=uuid.uuid4().hex,
            parent_node_id=stack[-1] if stack else None,
            depth=len(stack),
            node_name=name,
            node_type=node_type,
            status="RUNNING",
            start_time=time.time(),
            extra_data=extra_data or {},
        )
        self.runs[trace_id].nodes.append(node)
        _NODE_STACK.set(stack + (node.node_id,))
        return node

    def finish_node(self, node: TraceNode | None, status: str = "SUCCESS", error: str | None = None) -> None:
        if node is None:
            return
        node.status = status
        node.error_message = error
        node.end_time = time.time()
        node.duration_ms = (node.end_time - node.start_time) * 1000
        stack = _NODE_STACK.get()
        if stack and stack[-1] == node.node_id:
            _NODE_STACK.set(stack[:-1])


class trace_run:
    def __init__(self, trace_name: str, recorder: TraceRecorder, **extra_data: Any) -> None:
        self.trace_name = trace_name
        self.recorder = recorder
        self.extra_data = extra_data
        self.run: TraceRun | None = None

    def __enter__(self) -> TraceRun:
        self.run = self.recorder.start_run(self.trace_name, self.extra_data)
        return self.run

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.run:
            self.recorder.finish_run(
                self.run.trace_id,
                status="ERROR" if exc else "SUCCESS",
                error=f"{exc_type.__name__}: {exc}" if exc_type else None,
            )
        _TRACE_ID.set(None)
        _NODE_STACK.set(())
        return False
