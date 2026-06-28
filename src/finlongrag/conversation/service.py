"""Product conversation service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from finlongrag.conversation.memory import ConversationMemory
from finlongrag.core.schema import AnswerResult
from finlongrag.service.pipeline import FinLongRAGPipeline
from finlongrag.storage.repository import ConversationRecord, ConversationRepository, MessageRecord


@dataclass(frozen=True)
class ChatResponse:
    conversation: ConversationRecord
    user_message: MessageRecord
    assistant_message: MessageRecord
    result: AnswerResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "conversation": self.conversation.to_dict(),
            "user_message": self.user_message.to_dict(),
            "assistant_message": self.assistant_message.to_dict(),
            "result": self.result.to_dict(),
        }


class ChatService:
    def __init__(
        self,
        pipeline: FinLongRAGPipeline,
        repository: ConversationRepository,
        *,
        memory: ConversationMemory | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.repository = repository
        self.memory = memory or ConversationMemory()

    def create_conversation(self, *, title: str = "新对话", metadata: dict[str, Any] | None = None, user_id: str | None = None) -> ConversationRecord:
        return self.repository.create_conversation(title=title, metadata=metadata, user_id=user_id)

    def list_conversations(self, *, limit: int = 50, user_id: str | None = None) -> list[ConversationRecord]:
        return self.repository.list_conversations(limit=limit, user_id=user_id)

    def list_messages(self, conversation_id: str, *, limit: int = 100) -> list[MessageRecord]:
        return self.repository.list_messages(conversation_id, limit=limit)

    def ask(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        domain: str = "",
        doc_ids: list[str] | None = None,
        kb_id: str | None = None,
        kb_ids: list[str] | None = None,
    ) -> ChatResponse:
        conversation = self._ensure_conversation(conversation_id, message)
        previous_messages = self.repository.list_messages(conversation.conversation_id, limit=80)
        history = self.memory.build_context(conversation, previous_messages)
        user_message = self.repository.append_message(
            conversation.conversation_id,
            "user",
            message,
            metadata={
                "domain": domain,
                "doc_ids": doc_ids or [],
                "knowledge_base_id": kb_id or "",
                "kb_ids": kb_ids or []
            },
        )
        result = self.pipeline.ask(
            message,
            domain=domain,
            doc_ids=doc_ids or [],
            kb_id=kb_id,
            kb_ids=kb_ids,
            qid=f"chat_{conversation.conversation_id}_{user_message.message_id[:8]}",
            history=history,
        )
        assistant_message = self.repository.append_message(
            conversation.conversation_id,
            "assistant",
            result.answer,
            metadata={
                "qid": result.qid,
                "domain": result.domain,
                "answer_format": result.answer_format,
                "confidence": result.confidence,
                "token_usage": result.token_usage.to_dict(),
                "evidence": [item.to_dict() for item in result.evidence[:8]],
                "risk_flags": result.metadata.get("risk_flags", []),
                "trace_id": result.metadata.get("trace_id"),
            },
        )
        refreshed_messages = self.repository.list_messages(conversation.conversation_id, limit=80)
        self.repository.update_summary(
            conversation.conversation_id,
            self.memory.update_summary(conversation.summary, refreshed_messages),
        )
        updated = self.repository.get_conversation(conversation.conversation_id) or conversation
        return ChatResponse(updated, user_message, assistant_message, result)

    def _ensure_conversation(self, conversation_id: str | None, first_message: str) -> ConversationRecord:
        if conversation_id:
            existing = self.repository.get_conversation(conversation_id)
            if existing is not None:
                return existing
        return self.create_conversation(title=_title_from_message(first_message))


def _title_from_message(message: str) -> str:
    title = " ".join((message or "").split())
    return title[:32] or "新对话"
