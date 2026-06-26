"""FastAPI application for FinLongRAG backend and integrated frontend."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from finlongrag.api.schemas import (
    ApiResponse,
    ChatRequest,
    CreateConversationRequest,
    CreateKnowledgeBaseRequest,
    RegisterDocumentRequest,
    RunIngestionRequest,
)
from finlongrag.api.v1 import create_v1_router
from finlongrag.conversation.service import ChatService
from finlongrag.core.config import Settings
from finlongrag.knowledge.service import KnowledgeService
from finlongrag.service.pipeline import FinLongRAGPipeline
from finlongrag.storage.knowledge_repository import create_knowledge_repository
from finlongrag.storage.repository import create_conversation_repository


class SPAStaticFiles(StaticFiles):
    """Serve Vue history routes by falling back to index.html."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and "." not in path:
                return await super().get_response("index.html", scope)
            raise


def create_app(*, dry_run: bool = False) -> FastAPI:
    app = FastAPI(title="FinLongRAG API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @lru_cache(maxsize=1)
    def settings() -> Settings:
        loaded = Settings.from_file()
        loaded.ensure_dirs()
        return loaded

    @lru_cache(maxsize=1)
    def chat_service() -> ChatService:
        loaded = settings()
        repository = create_conversation_repository(loaded.database_url)
        pipeline = FinLongRAGPipeline(loaded, dry_run=dry_run)
        return ChatService(pipeline, repository)

    @lru_cache(maxsize=1)
    def knowledge_service() -> KnowledgeService:
        loaded = settings()
        return KnowledgeService(loaded, create_knowledge_repository(loaded.database_url))

    @app.get("/api/health")
    def health() -> ApiResponse:
        loaded = settings()
        kb_count = len(knowledge_service().list_knowledge_bases(limit=1000))
        document_count = len(knowledge_service().list_documents(limit=1000))
        active_index = knowledge_service().get_active_index_version()
        return ApiResponse(
            data={
                "status": "ok",
                "database_url": _redact_database_url(loaded.database_url),
                "index_ready": (loaded.index_dir / "bm25_index.pkl").exists(),
                "doc_index_ready": (loaded.index_dir / "document_index.pkl").exists(),
                "vector_index_ready": (loaded.index_dir / "vector_index.pkl").exists(),
                "vector_retrieval_enabled": loaded.enable_vector_retrieval,
                "vector_store": loaded.vector_store,
                "embedding_provider": loaded.vector_embedding_provider,
                "embedding_model": loaded.vector_embedding_model,
                "embedding_dimension": loaded.vector_dimension,
                "rerank_provider": loaded.rerank_provider,
                "rerank_model": loaded.rerank_model,
                "active_index_version": active_index.to_dict() if active_index else None,
                "knowledge_bases": kb_count,
                "knowledge_documents": document_count,
                "dry_run": dry_run,
            }
        )

    @app.post("/api/conversations")
    def create_conversation(payload: CreateConversationRequest) -> ApiResponse:
        conversation = chat_service().create_conversation(title=payload.title, metadata=payload.metadata)
        return ApiResponse(data=conversation.to_dict())

    @app.get("/api/conversations")
    def list_conversations(limit: int = Query(default=50, ge=1, le=200)) -> ApiResponse:
        conversations = chat_service().list_conversations(limit=limit)
        return ApiResponse(data=[item.to_dict() for item in conversations])

    @app.get("/api/conversations/{conversation_id}/messages")
    def list_messages(conversation_id: str, limit: int = Query(default=100, ge=1, le=300)) -> ApiResponse:
        if chat_service().repository.get_conversation(conversation_id) is None:
            raise HTTPException(status_code=404, detail="conversation not found")
        messages = chat_service().list_messages(conversation_id, limit=limit)
        return ApiResponse(data=[item.to_dict() for item in messages])

    @app.post("/api/chat")
    def chat(payload: ChatRequest) -> ApiResponse:
        response = chat_service().ask(
            payload.message,
            conversation_id=payload.conversation_id,
            domain=payload.domain,
            doc_ids=payload.doc_ids,
        )
        return ApiResponse(data=response.to_dict())

    @app.get("/api/chat/stream")
    def chat_stream(
        message: str = Query(min_length=1),
        conversation_id: str | None = None,
        domain: str = "",
        doc_ids: str = "",
    ) -> StreamingResponse:
        parsed_doc_ids = [item.strip() for item in doc_ids.split(",") if item.strip()]

        def event_stream():
            yield _sse("meta", {"conversation_id": conversation_id, "domain": domain, "doc_ids": parsed_doc_ids})
            try:
                response = chat_service().ask(
                    message,
                    conversation_id=conversation_id,
                    domain=domain,
                    doc_ids=parsed_doc_ids,
                )
                answer = response.result.answer
                for chunk in _chunks(answer, size=24):
                    yield _sse("message", {"type": "answer", "delta": chunk})
                yield _sse(
                    "finish",
                    {
                        "conversation_id": response.conversation.conversation_id,
                        "message_id": response.assistant_message.message_id,
                        "answer": answer,
                        "evidence": [item.to_dict() for item in response.result.evidence[:6]],
                        "token_usage": response.result.token_usage.to_dict(),
                        "metadata": response.result.metadata,
                    },
                )
                yield _sse("done", {})
            except Exception as exc:
                yield _sse("error", {"error": str(exc)})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/knowledge-bases")
    def create_knowledge_base(payload: CreateKnowledgeBaseRequest) -> ApiResponse:
        record = knowledge_service().create_knowledge_base(
            name=payload.name,
            description=payload.description,
            metadata=payload.metadata,
        )
        return ApiResponse(data=record.to_dict())

    @app.get("/api/knowledge-bases")
    def list_knowledge_bases(limit: int = Query(default=100, ge=1, le=500)) -> ApiResponse:
        records = knowledge_service().list_knowledge_bases(limit=limit)
        return ApiResponse(data=[record.to_dict() for record in records])

    @app.get("/api/knowledge-bases/{kb_id}")
    def get_knowledge_base(kb_id: str) -> ApiResponse:
        try:
            record = knowledge_service().get_knowledge_base(kb_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ApiResponse(data=record.to_dict())

    @app.get("/api/knowledge-bases/{kb_id}/documents")
    def list_knowledge_documents(kb_id: str, limit: int = Query(default=500, ge=1, le=2000)) -> ApiResponse:
        try:
            records = knowledge_service().list_documents(kb_id, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ApiResponse(data=[record.to_dict() for record in records])

    @app.post("/api/knowledge-bases/{kb_id}/documents")
    def register_knowledge_document(kb_id: str, payload: RegisterDocumentRequest) -> ApiResponse:
        try:
            record = knowledge_service().register_local_document(
                kb_id=kb_id,
                path=payload.path,
                domain=payload.domain,
                doc_id=payload.doc_id,
                title=payload.title,
                metadata=payload.metadata,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return ApiResponse(data=record.to_dict())

    def run_ingestion_background(task_id: str, build_index: bool) -> None:
        task = knowledge_service().run_ingestion_task(task_id, raise_on_error=False)
        if build_index and task.status == "succeeded":
            chat_service.cache_clear()

    @app.post("/api/knowledge-bases/{kb_id}/ingest")
    def ingest_knowledge_base(
        kb_id: str,
        payload: RunIngestionRequest,
        background_tasks: BackgroundTasks,
    ) -> ApiResponse:
        try:
            if payload.async_mode:
                task = knowledge_service().create_ingestion_task(
                    kb_id,
                    build_index=payload.build_index,
                    status="queued",
                    stage="queued",
                    metadata={"execution_mode": "background"},
                )
                background_tasks.add_task(run_ingestion_background, task.task_id, payload.build_index)
            else:
                task = knowledge_service().ingest_knowledge_base(kb_id, build_index=payload.build_index)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if payload.build_index and task.status == "succeeded":
            chat_service.cache_clear()
        return ApiResponse(data=task.to_dict())

    @app.get("/api/ingestion/tasks")
    def list_ingestion_tasks(
        kb_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> ApiResponse:
        try:
            records = knowledge_service().list_tasks(kb_id, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ApiResponse(data=[record.to_dict() for record in records])

    @app.get("/api/ingestion/tasks/{task_id}")
    def get_ingestion_task(task_id: str) -> ApiResponse:
        try:
            record = knowledge_service().get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ApiResponse(data=record.to_dict())

    @app.get("/api/index-versions")
    def list_index_versions(
        kb_id: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> ApiResponse:
        try:
            records = knowledge_service().list_index_versions(kb_id, limit=limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return ApiResponse(data=[record.to_dict() for record in records])

    @app.get("/api/index-versions/active")
    def get_active_index_version() -> ApiResponse:
        record = knowledge_service().get_active_index_version()
        return ApiResponse(data=record.to_dict() if record else None)

    @app.post("/api/index-versions/{index_version_id}/activate")
    def activate_index_version(index_version_id: str) -> ApiResponse:
        try:
            record = knowledge_service().activate_index_version(index_version_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        chat_service.cache_clear()
        return ApiResponse(data=record.to_dict())

    app.include_router(
        create_v1_router(
            settings_provider=settings,
            chat_service_provider=chat_service,
            knowledge_service_provider=knowledge_service,
            clear_chat_cache=chat_service.cache_clear,
            dry_run=dry_run,
        ),
        prefix="/api/v1",
    )

    frontend_dist = settings().project_root / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")

    return app


def _sse(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _chunks(text: str, *, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [""]


def _redact_database_url(database_url: str) -> str:
    return "<configured>"
