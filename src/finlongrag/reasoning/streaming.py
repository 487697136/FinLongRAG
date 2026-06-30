"""Streaming answer events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finlongrag.core.schema import AnswerResult


@dataclass
class AnswerStreamEvent:
    """Incremental stream event from the reasoning pipeline."""

    content: str = ""
    status: str | None = None
    done: bool = False
    result: AnswerResult | None = None
    chat: Any | None = None
