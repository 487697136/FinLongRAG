"""Conversation / message schema.

`Conversation.summary` stays a denormalized "current" field matching the
existing `ConversationRecord.summary` contract that `ChatService` and
`ConversationMemory` already read/write (see conversation/memory.py and
storage/repository.py) — `SQLAlchemyConversationRepository` must keep filling
it the same way. `ConversationSummary` is an additive history table (one row
per rolling-summary update) for future auditing/debugging; it does not
replace the denormalized field.

`Message.intent` and `Message.latency_ms` are promoted to first-class columns
(not buried in metadata) because Phase 7's dashboard aggregation needs to
group/filter on them directly. Everything else the pipeline already produces
(evidence, citations, token_usage, trace_id, risk_flags) keeps living in the
JSON `metadata` column, unchanged from current behavior.
"""

from __future__ import annotations

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from finlongrag.db.base import Base, JSONVariant, TimestampMixin, new_id


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500), default="")
    summary: Mapped[str] = mapped_column(String, default="")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONVariant, default=dict)
    deleted_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.conversation_id"), index=True
    )
    summary_text: Mapped[str] = mapped_column(String, default="")
    covers_up_to_message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default="now()")


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.conversation_id"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String, default="")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONVariant, default=dict)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default="now()")


class MessageFeedback(Base):
    __tablename__ = "message_feedback"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(String(32), ForeignKey("messages.message_id"), index=True)
    rating: Mapped[str] = mapped_column(String(8))
    comment: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default="now()")
