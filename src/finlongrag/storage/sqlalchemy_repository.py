"""SQLAlchemy-backed `ConversationRepository` for PostgreSQL.

The public repository protocol is synchronous, so this implementation uses
SQLAlchemy's sync engine with Psycopg 3.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select

from finlongrag.db import get_sync_sessionmaker
from finlongrag.db.models.conversation import Conversation, ConversationSummary, Message, MessageFeedback
from finlongrag.storage.repository import ConversationRecord, MessageRecord


class SQLAlchemyConversationRepository:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._sessionmaker = get_sync_sessionmaker(database_url)

    def create_conversation(
        self, *, title: str = "新对话", metadata: dict[str, Any] | None = None, user_id: str | None = None
    ) -> ConversationRecord:
        now = _now()
        row = Conversation(
            conversation_id=uuid.uuid4().hex,
            user_id=user_id,  # 设置用户 ID
            title=title.strip() or "新对话",
            summary="",
            metadata_json=metadata or {},
            created_at=now,
            updated_at=now,
        )
        with self._sessionmaker() as session:
            session.add(row)
            session.commit()
            return _conversation_from_model(row)

    def list_conversations(self, *, limit: int = 50, user_id: str | None = None) -> list[ConversationRecord]:
        with self._sessionmaker() as session:
            stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
            # 用户隔离：只返回该用户的会话
            if user_id:
                stmt = stmt.where(Conversation.user_id == user_id)
            rows = session.scalars(stmt).all()
            return [_conversation_from_model(row) for row in rows]

    def get_conversation(self, conversation_id: str, user_id: str | None = None) -> ConversationRecord | None:
        with self._sessionmaker() as session:
            row = session.get(Conversation, conversation_id)
            if row is None:
                return None
            # 用户隔离：只允许访问自己的会话
            if user_id and row.user_id != user_id:
                return None
            return _conversation_from_model(row)

    def list_messages(self, conversation_id: str, *, limit: int = 100) -> list[MessageRecord]:
        with self._sessionmaker() as session:
            rows = session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.desc())
                .limit(limit)
            ).all()
            return list(reversed([_message_from_model(row) for row in rows]))

    def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> MessageRecord:
        if role not in {"user", "assistant", "system"}:
            raise ValueError(f"unsupported message role: {role}")
        now = _now()
        with self._sessionmaker() as session:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None:
                raise KeyError(f"conversation not found: {conversation_id}")
            meta = dict(metadata or {})
            row = Message(
                message_id=uuid.uuid4().hex,
                conversation_id=conversation_id,
                role=role,
                content=content,
                metadata_json=meta,
                intent=meta.get("intent"),
                latency_ms=meta.get("latency_ms"),
                created_at=now,
            )
            session.add(row)
            conversation.updated_at = now
            session.commit()
            return _message_from_model(row)

    def update_summary(self, conversation_id: str, summary: str) -> None:
        with self._sessionmaker() as session:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None:
                raise KeyError(f"conversation not found: {conversation_id}")
            conversation.summary = summary
            conversation.updated_at = _now()
            session.commit()

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._sessionmaker() as session:
            conversation = session.get(Conversation, conversation_id)
            if conversation is None:
                return False
            message_ids = session.scalars(
                select(Message.message_id).where(Message.conversation_id == conversation_id)
            ).all()
            if message_ids:
                session.execute(delete(MessageFeedback).where(MessageFeedback.message_id.in_(message_ids)))
            session.execute(delete(ConversationSummary).where(ConversationSummary.conversation_id == conversation_id))
            session.execute(delete(Message).where(Message.conversation_id == conversation_id))
            session.delete(conversation)
            session.commit()
            return True


def _now() -> datetime:
    return datetime.now(UTC)


def _conversation_from_model(row: Conversation) -> ConversationRecord:
    return ConversationRecord(
        conversation_id=row.conversation_id,
        title=row.title,
        summary=row.summary or "",
        created_at=row.created_at.timestamp() if row.created_at else 0.0,
        updated_at=row.updated_at.timestamp() if row.updated_at else 0.0,
        metadata=dict(row.metadata_json or {}),
    )


def _message_from_model(row: Message) -> MessageRecord:
    return MessageRecord(
        message_id=row.message_id,
        conversation_id=row.conversation_id,
        role=row.role,
        content=row.content,
        created_at=row.created_at.timestamp() if row.created_at else 0.0,
        metadata=dict(row.metadata_json or {}),
    )
