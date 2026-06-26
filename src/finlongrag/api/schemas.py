"""API request and response models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str = "新对话"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    domain: str = ""
    doc_ids: list[str] = Field(default_factory=list)


class CreateKnowledgeBaseRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegisterDocumentRequest(BaseModel):
    path: str = Field(min_length=1)
    domain: str = ""
    doc_id: str | None = None
    title: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunIngestionRequest(BaseModel):
    build_index: bool = True
    async_mode: bool = True


class ApiResponse(BaseModel):
    success: bool = True
    data: Any = None
    error: str | None = None
