"""Conversation repository contracts and PostgreSQL factory."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    title: str
    summary: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MessageRecord:
    message_id: str
    conversation_id: str
    role: str
    content: str
    created_at: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConversationRepository(Protocol):
    def create_conversation(
        self,
        *,
        title: str = "新对话",
        metadata: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> ConversationRecord:
        ...

    def list_conversations(self, *, limit: int = 50, user_id: str | None = None) -> list[ConversationRecord]:
        ...

    def get_conversation(self, conversation_id: str, user_id: str | None = None) -> ConversationRecord | None:
        ...

    def list_messages(self, conversation_id: str, *, limit: int = 100) -> list[MessageRecord]:
        ...

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> MessageRecord:
        ...

    def update_summary(self, conversation_id: str, summary: str) -> None:
        ...

    def delete_conversation(self, conversation_id: str) -> bool:
        ...


def create_conversation_repository(database_url: str) -> ConversationRepository:
    from finlongrag.db.session import is_postgres_url

    if not is_postgres_url(database_url):
        raise ValueError("FinLongRAG now requires PostgreSQL 18; SQLite is not supported.")
    from finlongrag.storage.sqlalchemy_repository import SQLAlchemyConversationRepository

    return SQLAlchemyConversationRepository(database_url)
