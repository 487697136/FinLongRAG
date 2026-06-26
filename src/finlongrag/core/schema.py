"""Stable data contracts for FinLongRAG.

These dataclasses are intentionally small and serializable. They are the shared
boundary between ingestion, indexing, retrieval, reasoning, and service layers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

AnswerFormat = Literal["mcq", "multi", "tf", "open"]
VerdictLabel = Literal["true", "false", "insufficient"]


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.total_tokens == 0 and (self.prompt_tokens or self.completion_tokens):
            self.total_tokens = self.prompt_tokens + self.completion_tokens

    def add(self, other: TokenUsage) -> TokenUsage:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        return self

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class Question:
    qid: str
    question: str
    domain: str = ""
    options: dict[str, str] = field(default_factory=dict)
    answer_format: AnswerFormat = "open"
    split: str = ""
    qtype: str = ""
    doc_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Question:
        options = {str(k): str(v).strip() for k, v in dict(data.get("options") or {}).items()}
        answer_format = str(data.get("answer_format") or ("open" if not options else "mcq"))
        return cls(
            qid=str(data.get("qid") or "adhoc"),
            question=str(data.get("question") or "").strip(),
            domain=str(data.get("domain") or ""),
            options=options,
            answer_format=answer_format,  # type: ignore[arg-type]
            split=str(data.get("split") or ""),
            qtype=str(data.get("type") or data.get("qtype") or ""),
            doc_ids=[str(item) for item in data.get("doc_ids") or []],
            metadata=dict(data.get("metadata") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["type"] = data.pop("qtype")
        return data

    def options_text(self) -> str:
        return "\n".join(f"{key}. {value}" for key, value in sorted(self.options.items()))


@dataclass
class Document:
    doc_id: str
    domain: str
    title: str
    path: str
    raw_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def path_obj(self) -> Path:
        return Path(self.path)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Document:
        return cls(**data)


@dataclass
class PageText:
    doc_id: str
    domain: str
    page: int
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    domain: str
    text: str
    page: int | None = None
    section: str = ""
    clause_id: str = ""
    numbers: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chunk:
        return cls(**data)


@dataclass
class RetrievalResult:
    chunk_id: str
    doc_id: str
    domain: str
    evidence_text: str
    score: float
    source: str
    query: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetrievalResult:
        return cls(**data)


@dataclass
class Claim:
    claim_id: str
    question_id: str
    option_key: str
    option_text: str
    claim_text: str
    source_question: str
    answer_format: AnswerFormat
    domain: str
    doc_scope: list[str] = field(default_factory=list)
    claim_type: str = "fact"
    entities: list[str] = field(default_factory=list)
    numbers: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    must_terms: list[str] = field(default_factory=list)
    should_terms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimVerdict:
    claim_id: str
    option_key: str
    label: VerdictLabel
    confidence: float
    evidence: list[RetrievalResult] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        return data


@dataclass
class AnswerResult:
    qid: str
    answer: str
    domain: str
    answer_format: AnswerFormat
    confidence: float = 0.0
    evidence: list[RetrievalResult] = field(default_factory=list)
    verdicts: list[ClaimVerdict] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    raw_response: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = [item.to_dict() for item in self.evidence]
        data["verdicts"] = [item.to_dict() for item in self.verdicts]
        data["token_usage"] = self.token_usage.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AnswerResult:
        return cls(
            qid=str(data["qid"]),
            answer=str(data.get("answer") or ""),
            domain=str(data.get("domain") or ""),
            answer_format=data.get("answer_format", "open"),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            evidence=[RetrievalResult.from_dict(row) for row in data.get("evidence", [])],
            verdicts=[],
            token_usage=TokenUsage(**data.get("token_usage", {})),
            raw_response=str(data.get("raw_response") or ""),
            metadata=dict(data.get("metadata") or {}),
        )
