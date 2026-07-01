"""Product conversation service."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from finlongrag.conversation.memory import ConversationMemory
from finlongrag.core.schema import AnswerResult
from finlongrag.reasoning.streaming import AnswerStreamEvent
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
        user_id: str | None = None,
        domain: str = "",
        doc_ids: list[str] | None = None,
        kb_id: str | None = None,
        kb_ids: list[str] | None = None,
        use_memory: bool = True,
        mode: str = "auto",
        top_k: int | None = None,
        memory_turn_window: int | None = None,
        llm_model: str | None = None,
    ) -> ChatResponse:
        conversation = self._ensure_conversation(conversation_id, message, user_id=user_id)
        previous_messages = self.repository.list_messages(conversation.conversation_id, limit=80)

        # Build conversation context — respects use_memory flag
        history = self.memory.build_context(
            conversation,
            previous_messages,
            use_memory=use_memory,
            memory_turn_window=memory_turn_window,
        )

        # Extract persistent entity context for multi-turn inheritance
        history_entities: dict[str, Any] = {}
        if use_memory and previous_messages:
            history_entities = self.memory.extract_entity_context(previous_messages)

        user_message = self.repository.append_message(
            conversation.conversation_id,
            "user",
            message,
            metadata={
                "domain": domain,
                "doc_ids": doc_ids or [],
                "knowledge_base_id": kb_id or "",
                "kb_ids": kb_ids or [],
                "use_memory": use_memory,
                "mode": mode,
                "top_k": top_k,
                "llm_model": llm_model,
            },
        )
        try:
            result = self.pipeline.ask(
                message,
                domain=domain,
                doc_ids=doc_ids or [],
                kb_id=kb_id,
                kb_ids=kb_ids,
                qid=f"chat_{conversation.conversation_id}_{user_message.message_id[:8]}",
                history=history,
                history_entities=history_entities if use_memory else {},
                mode=mode,
                top_k=top_k,
                llm_model=llm_model,
            )
        except Exception as exc:
            self.repository.append_message(
                conversation.conversation_id,
                "assistant",
                "抱歉，处理您的问题时出现错误，请稍后重试。",
                metadata={"failed": True, "error": str(exc)},
            )
            raise
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
                "citations": result.metadata.get("citations", []),
                # Agent traceability — persisted so session history can replay them
                "route": result.metadata.get("route", {}),
                "strategy": result.metadata.get("strategy", ""),
                "plan": result.metadata.get("plan", {}),
                "gated": result.metadata.get("gated", False),
                "mode": mode,
            },
        )
        # Update rolling summary (may use LLM if turn count is high)
        refreshed_messages = self.repository.list_messages(conversation.conversation_id, limit=80)
        self.repository.update_summary(
            conversation.conversation_id,
            self.memory.update_summary(conversation.summary, refreshed_messages),
        )
        updated = self.repository.get_conversation(conversation.conversation_id) or conversation
        return ChatResponse(updated, user_message, assistant_message, result)

    def ask_stream(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        user_id: str | None = None,
        domain: str = "",
        doc_ids: list[str] | None = None,
        kb_id: str | None = None,
        kb_ids: list[str] | None = None,
        use_memory: bool = True,
        mode: str = "auto",
        top_k: int | None = None,
        memory_turn_window: int | None = None,
        llm_model: str | None = None,
    ) -> Iterator[AnswerStreamEvent]:
        conversation = self._ensure_conversation(conversation_id, message, user_id=user_id)
        previous_messages = self.repository.list_messages(conversation.conversation_id, limit=80)
        history = self.memory.build_context(
            conversation,
            previous_messages,
            use_memory=use_memory,
            memory_turn_window=memory_turn_window,
        )
        history_entities: dict[str, Any] = {}
        if use_memory and previous_messages:
            history_entities = self.memory.extract_entity_context(previous_messages)

        user_message = self.repository.append_message(
            conversation.conversation_id,
            "user",
            message,
            metadata={
                "domain": domain,
                "doc_ids": doc_ids or [],
                "knowledge_base_id": kb_id or "",
                "kb_ids": kb_ids or [],
                "use_memory": use_memory,
                "mode": mode,
                "top_k": top_k,
                "llm_model": llm_model,
            },
        )

        try:
            for event in self.pipeline.ask_stream(
                message,
                domain=domain,
                doc_ids=doc_ids or [],
                kb_id=kb_id,
                kb_ids=kb_ids,
                qid=f"chat_{conversation.conversation_id}_{user_message.message_id[:8]}",
                history=history,
                history_entities=history_entities if use_memory else {},
                mode=mode,
                top_k=top_k,
                llm_model=llm_model,
            ):
                if event.done and event.result is not None:
                    result = event.result
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
                            "citations": result.metadata.get("citations", []),
                            "route": result.metadata.get("route", {}),
                            "strategy": result.metadata.get("strategy", ""),
                            "plan": result.metadata.get("plan", {}),
                            "gated": result.metadata.get("gated", False),
                            "mode": mode,
                        },
                    )
                    refreshed_messages = self.repository.list_messages(conversation.conversation_id, limit=80)
                    self.repository.update_summary(
                        conversation.conversation_id,
                        self.memory.update_summary(conversation.summary, refreshed_messages),
                    )
                    updated = self.repository.get_conversation(conversation.conversation_id) or conversation
                    event.chat = ChatResponse(updated, user_message, assistant_message, result)
                yield event
        except Exception as exc:
            self.repository.append_message(
                conversation.conversation_id,
                "assistant",
                "抱歉，处理您的问题时出现错误，请稍后重试。",
                metadata={"failed": True, "error": str(exc)},
            )
            raise

    def _ensure_conversation(
        self,
        conversation_id: str | None,
        first_message: str,
        *,
        user_id: str | None = None,
    ) -> ConversationRecord:
        if conversation_id:
            existing = self.repository.get_conversation(conversation_id, user_id=user_id)
            if existing is not None:
                return existing
            if user_id is not None:
                raise KeyError(f"conversation not found: {conversation_id}")
        return self.create_conversation(title=_title_from_message(first_message), user_id=user_id)


def _title_from_message(message: str) -> str:
    title = " ".join((message or "").split())
    return title[:32] or "新对话"
