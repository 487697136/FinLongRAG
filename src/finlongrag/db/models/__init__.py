"""ORM model registry.

Importing this module registers every mapped class against `Base.metadata`,
which is required before `Base.metadata.create_all()` or Alembic autogeneration
can see the full schema.
"""

from __future__ import annotations

from finlongrag.db.models.conversation import Conversation, ConversationSummary, Message, MessageFeedback
from finlongrag.db.models.intent import IntentNode
from finlongrag.db.models.knowledge import (
    IndexVersion,
    IngestionTask,
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeChunkLog,
    KnowledgeDocument,
)
from finlongrag.db.models.trace import TraceNode, TraceRun
from finlongrag.db.models.user import User

__all__ = [
    "Conversation",
    "ConversationSummary",
    "Message",
    "MessageFeedback",
    "IntentNode",
    "IngestionTask",
    "IndexVersion",
    "KnowledgeBase",
    "KnowledgeChunk",
    "KnowledgeChunkLog",
    "KnowledgeDocument",
    "TraceNode",
    "TraceRun",
    "User",
]
