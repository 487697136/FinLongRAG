"""Lightweight intent resolution for retrieval and tool hints.

Inspired by ragent's intent tree, but kept config-driven and stateless for product use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from finlongrag.core.config import Settings
from finlongrag.core.schema import Question

_DEFAULT_INTENTS: list[dict[str, Any]] = [
    {
        "id": "financial_metrics",
        "name": "财务指标与计算",
        "keywords": ["营业收入", "净利润", "同比", "环比", "占比", "增长率"],
        "tools": ["calculator"],
        "domains": ["financial_reports"],
        "dense_evidence": True,
    },
]


@dataclass(frozen=True)
class ResolvedIntent:
    intent_id: str
    name: str
    score: float
    tools: tuple[str, ...] = ()
    domains: tuple[str, ...] = ()
    dense_evidence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "name": self.name,
            "score": self.score,
            "tools": list(self.tools),
            "domains": list(self.domains),
            "dense_evidence": self.dense_evidence,
        }


@dataclass(frozen=True)
class IntentResolution:
    intents: list[ResolvedIntent]
    use_calculator: bool = False
    dense_evidence: bool = False
    domain_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "intents": [item.to_dict() for item in self.intents],
            "use_calculator": self.use_calculator,
            "dense_evidence": self.dense_evidence,
            "domain_hints": list(self.domain_hints),
        }


class IntentResolver:
    """Keyword-based intent matcher loaded from config/intents.yaml."""

    def __init__(self, settings: Settings | None = None, *, intents: list[dict[str, Any]] | None = None) -> None:
        self.settings = settings or Settings.from_file()
        self._intents = intents if intents is not None else _load_intent_config(self.settings)

    def resolve(self, question: Question) -> IntentResolution:
        text = f"{question.question} {' '.join(question.options.values())}".strip().lower()
        scored: list[ResolvedIntent] = []
        for row in self._intents:
            keywords = [str(k).lower() for k in row.get("keywords") or []]
            hits = sum(1 for keyword in keywords if keyword and keyword in text)
            if hits <= 0:
                continue
            score = min(1.0, hits / max(1, min(3, len(keywords))))
            scored.append(
                ResolvedIntent(
                    intent_id=str(row.get("id") or row.get("name") or "intent"),
                    name=str(row.get("name") or row.get("id") or "intent"),
                    score=round(score, 3),
                    tools=tuple(str(t) for t in row.get("tools") or []),
                    domains=tuple(str(d) for d in row.get("domains") or []),
                    dense_evidence=bool(row.get("dense_evidence")),
                )
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        top = scored[:3]
        use_calculator = any("calculator" in intent.tools for intent in top)
        dense_evidence = any(intent.dense_evidence for intent in top)
        domain_hints = list(dict.fromkeys(domain for intent in top for domain in intent.domains))
        if question.domain and question.domain not in domain_hints:
            domain_hints.insert(0, question.domain)
        return IntentResolution(
            intents=top,
            use_calculator=use_calculator,
            dense_evidence=dense_evidence,
            domain_hints=domain_hints,
        )


def _load_intent_config(settings: Settings) -> list[dict[str, Any]]:
    path = settings.project_root / "config" / "intents.yaml"
    if not path.exists():
        return list(_DEFAULT_INTENTS)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = data.get("intents")
    return rows if isinstance(rows, list) and rows else list(_DEFAULT_INTENTS)
