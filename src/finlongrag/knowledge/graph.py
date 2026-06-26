"""Knowledge graph abstraction.

This module intentionally defines contracts only. A future graph backend can
implement these interfaces without changing the agent or retrieval pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class GraphEntity:
    entity_id: str
    name: str
    entity_type: str = ""
    aliases: tuple[str, ...] = ()
    properties: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GraphRelation:
    source_id: str
    target_id: str
    relation_type: str
    evidence: str = ""
    properties: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GraphSearchResult:
    entities: list[GraphEntity]
    relations: list[GraphRelation]
    source: str = "knowledge_graph"

    def to_dict(self) -> dict:
        return {
            "entities": [entity.to_dict() for entity in self.entities],
            "relations": [relation.to_dict() for relation in self.relations],
            "source": self.source,
        }


class KnowledgeGraphStore(Protocol):
    def search(self, query: str, *, domain: str = "", top_k: int = 10) -> GraphSearchResult:
        ...


class EmptyKnowledgeGraphStore:
    """Default no-op graph store used before a real KG exists."""

    def search(self, query: str, *, domain: str = "", top_k: int = 10) -> GraphSearchResult:
        return GraphSearchResult(entities=[], relations=[], source="empty")

