"""Persistence layer for product-facing FinLongRAG services."""

from finlongrag.storage.knowledge_repository import (
    IndexVersionRecord,
    IngestionTaskRecord,
    KnowledgeBaseRecord,
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    create_knowledge_repository,
)
from finlongrag.storage.repository import (
    ConversationRecord,
    ConversationRepository,
    MessageRecord,
    create_conversation_repository,
)
from finlongrag.storage.sqlalchemy_repository import SQLAlchemyConversationRepository

__all__ = [
    "ConversationRecord",
    "ConversationRepository",
    "IndexVersionRecord",
    "IngestionTaskRecord",
    "KnowledgeBaseRecord",
    "KnowledgeChunkRecord",
    "KnowledgeDocumentRecord",
    "MessageRecord",
    "SQLAlchemyConversationRepository",
    "create_conversation_repository",
    "create_knowledge_repository",
]
