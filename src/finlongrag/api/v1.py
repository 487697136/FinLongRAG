"""Versioned API adapter for the product frontend."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shutil
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import base64
import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from finlongrag.api.helpers import (
    UploadTooLargeError,
    get_user_kb,
    read_upload_limited,
    redact_database_url,
    resolve_query_kb_scope,
    validate_upload_filename,
)
from finlongrag.core.api_key_context import load_user_api_key, user_api_key_scope
from finlongrag.core.secrets import decrypt_secret, encrypt_secret
from finlongrag.conversation.service import ChatService
from finlongrag.core.config import Settings, get_api_key
from finlongrag.db import get_sync_sessionmaker
from finlongrag.db.models.api_key import UserApiKey
from finlongrag.db.models.user import User
from finlongrag.evaluation_center.loader import load_test_set
from finlongrag.evaluation_center.repository import EvaluationRepository, now_iso
from finlongrag.evaluation_center.runner import run_retrieval_evaluation
from finlongrag.evaluation_center.schemas import EvalConfig, EvalReport, RetrievalStrategy
from finlongrag.index.faiss_store import _safe_id
from finlongrag.knowledge.service import KnowledgeService
from finlongrag.storage.knowledge_repository import KnowledgeDocumentRecord
from finlongrag.tasks.local import get_default_executor

security = HTTPBearer(auto_error=False)
QueryMode = Literal["auto", "naive", "bm25", "llm_only"]


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str = Field(min_length=6)
    full_name: str = ""


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    enable_local: bool = True
    enable_naive_rag: bool = True
    enable_bm25: bool = True


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    knowledge_base_id: str | int | None = None
    kb_ids: list[str] | None = None  # 多知识库融合模式
    session_id: str | int | None = None
    mode: QueryMode = "auto"
    top_k: int = Field(default=20, ge=1, le=50)
    use_memory: bool = True
    memory_turn_window: int = Field(default=4, ge=0, le=20)
    llm_provider: str | None = None
    llm_model: str | None = None


class ApiKeySaveRequest(BaseModel):
    provider: str
    api_key: str
    description: str | None = None
    model_name: str | None = None


class CreateEvaluationRequest(BaseModel):
    kb_id: str
    test_set_id: str
    strategy: RetrievalStrategy = RetrievalStrategy.hybrid
    top_k: int = Field(default=8, ge=1, le=50)


def create_v1_router(
    *,
    settings_provider: Callable[[], Settings],
    chat_service_provider: Callable[[], ChatService],
    knowledge_service_provider: Callable[[], KnowledgeService],
    clear_chat_cache: Callable[[], None],
    dry_run: bool = False,
) -> APIRouter:
    router = APIRouter()
    auth = AuthService(settings_provider)
    executor = get_default_executor()
    # in-memory env key (read-only placeholder for environment-injected keys)
    _env_api_keys: dict[str, dict[str, Any]] = _initial_api_keys()

    def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> User:
        return auth.current_user(credentials)

    def evaluation_repository() -> EvaluationRepository:
        return EvaluationRepository(settings_provider().database_url)

    def run_ingestion_task(task_id: str, *, build_index: bool) -> None:
        task = knowledge_service_provider().run_ingestion_task(task_id, raise_on_error=False)
        if build_index and task.status == "succeeded":
            clear_chat_cache()

    def submit_ingestion(
        kb_id: str,
        *,
        build_index: bool = True,
        document_ids: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        task = knowledge_service_provider().create_ingestion_task(
            kb_id,
            build_index=build_index,
            status="queued",
            stage="queued",
            metadata={"execution_mode": "local_thread"},
            document_ids=document_ids,
            force=force,
        )
        executor.submit(task.task_id, run_ingestion_task, task.task_id, build_index=build_index)
        return task.to_dict()

    @router.post("/auth/register", status_code=status.HTTP_201_CREATED)
    def register(payload: RegisterRequest) -> dict[str, Any]:
        return auth.register(payload)

    @router.post("/auth/login")
    def login(username: str = Form(...), password: str = Form(...)) -> dict[str, str]:
        return auth.login(username, password)

    @router.get("/auth/me")
    def me(user: User = Depends(current_user)) -> dict[str, Any]:
        return auth.serialize_user(user)

    @router.post("/auth/change-password")
    def change_password(payload: ChangePasswordRequest, user: User = Depends(current_user)) -> dict[str, str]:
        auth.change_password(user, payload.old_password, payload.new_password)
        return {"message": "Password updated successfully."}

    def _api_key_sessionmaker():
        return get_sync_sessionmaker(settings_provider().database_url)

    def _load_db_api_keys(user_id: str) -> list[dict[str, Any]]:
        """Load persisted API keys for a user from DB."""
        try:
            with _api_key_sessionmaker()() as session:
                rows = session.execute(select(UserApiKey).where(UserApiKey.user_id == user_id)).scalars().all()
                return [
                    {
                        "id": row.id,
                        "provider": row.provider,
                        "description": row.description,
                        "model_name": row.model_name,
                        "key_preview": row.key_preview,
                        "created_at": row.created_at.isoformat() if row.created_at else "",
                    }
                    for row in rows
                ]
        except Exception:
            return []

    @router.get("/api-keys/")
    def list_api_keys(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        db_keys = [dict(item, api_key="") for item in _load_db_api_keys(user.id)]
        env_keys = [dict(item, api_key="") for item in _env_api_keys.values()]
        return env_keys + db_keys

    @router.get("/api-keys/providers")
    def list_providers(user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        return {
            "dashscope": {
                "label": "DashScope / Qwen",
                "type": "llm",
                "default_models": ["qwen-plus", "qwen-turbo", "qwen-max"],
            },
            "dashscope_embedding": {
                "label": "DashScope Embedding",
                "type": "embedding",
                "default_models": ["text-embedding-v4", "text-embedding-v3"],
                "enabled": True,
            },
            "dashscope_rerank": {
                "label": "DashScope Rerank",
                "type": "rerank",
                "default_models": ["qwen3-rerank", "gte-rerank-v2"],
                "enabled": True,
            },
        }

    def _resolve_llm_model(payload: QueryRequest, user_id: str) -> str | None:
        if payload.llm_model:
            return payload.llm_model
        if not payload.llm_provider:
            return None
        try:
            with _api_key_sessionmaker()() as session:
                row = session.execute(
                    select(UserApiKey)
                    .where(UserApiKey.user_id == user_id, UserApiKey.provider == payload.llm_provider)
                    .order_by(UserApiKey.created_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                if row and row.model_name:
                    return row.model_name
        except Exception:
            return None
        return None

    @router.post("/api-keys/")
    def save_api_key(payload: ApiKeySaveRequest, user: User = Depends(current_user)) -> dict[str, Any]:
        key_id = uuid.uuid4().hex
        key_encrypted = encrypt_secret(payload.api_key)
        preview = _mask_key(payload.api_key)
        try:
            with _api_key_sessionmaker()() as session:
                row = UserApiKey(
                    id=key_id,
                    user_id=user.id,
                    provider=payload.provider,
                    description=payload.description or payload.provider,
                    model_name=payload.model_name,
                    key_preview=preview,
                    key_encrypted=key_encrypted,
                )
                session.add(row)
                session.commit()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to save API key: {exc}") from exc
        return {
            "id": key_id,
            "provider": payload.provider,
            "description": payload.description or payload.provider,
            "model_name": payload.model_name,
            "key_preview": preview,
            "created_at": now_iso(),
            "api_key": "",
        }

    @router.delete("/api-keys/{key_id}")
    def delete_api_key(key_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        if key_id.startswith("env-"):
            raise HTTPException(status_code=400, detail="Environment-provided keys cannot be deleted here.")
        deleted_plain = ""
        try:
            with _api_key_sessionmaker()() as session:
                row = session.execute(
                    select(UserApiKey).where(UserApiKey.id == key_id, UserApiKey.user_id == user.id)
                ).scalar_one_or_none()
                if row is None:
                    raise HTTPException(status_code=404, detail="API key not found.")
                deleted_plain = decrypt_secret(row.key_encrypted)
                session.delete(row)
                session.commit()
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to delete API key: {exc}") from exc
        if deleted_plain and os.environ.get("DASHSCOPE_API_KEY") == deleted_plain:
            os.environ.pop("DASHSCOPE_API_KEY", None)
        return {"deleted": True}

    @router.get("/api-keys/runtime-status")
    def runtime_status(user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        settings = settings_provider()
        return {
            "app": {"name": "FinLongRAG", "version": "0.1.0", "dry_run": dry_run},
            "database_url": redact_database_url(settings.database_url),
            "graph_backend_requested": "postgresql_jsonb",
            "neo4j": {"configured": False, "connected": False, "url": ""},
            "upload": {
                "max_upload_size": settings.upload_max_bytes,
                "allowed_extensions": list(settings.upload_allowed_extensions),
            },
            "paths": {
                "workspace_root": str(settings.project_root),
                "upload_root": str(settings.object_storage_root),
                "index_root": str(settings.index_dir),
            },
            "configured_models": {"best": settings.qwen_model, "cheap": "qwen-turbo"},
        }

    @router.get("/knowledge-bases/")
    def list_knowledge_bases(
        limit: int = Query(default=100, ge=1, le=500),
        user: User = Depends(current_user),
    ) -> list[dict[str, Any]]:
        # 用户隔离：只返回当前用户创建的知识库
        return [_kb_payload(kb, knowledge_service_provider()) for kb in knowledge_service_provider().list_knowledge_bases(limit=limit, user_id=user.id)]

    @router.post("/knowledge-bases/", status_code=status.HTTP_201_CREATED)
    def create_knowledge_base(payload: KnowledgeBaseCreateRequest, user: User = Depends(current_user)) -> dict[str, Any]:
        kb = knowledge_service_provider().create_knowledge_base(
            name=payload.name,
            description=payload.description,
            created_by=user.id,
            metadata={
                "owner_id": user.id,
                "tenant_id": user.id,
                "enable_local": payload.enable_local,
                "enable_naive_rag": payload.enable_naive_rag,
                "enable_bm25": payload.enable_bm25,
            },
        )
        return _kb_payload(kb, knowledge_service_provider())

    @router.get("/knowledge-bases/{kb_id}")
    def get_knowledge_base(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        # 用户隔离：只允许访问自己创建的知识库
        try:
            kb = knowledge_service_provider().get_knowledge_base(kb_id, user_id=user.id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _kb_payload(kb, knowledge_service_provider())

    @router.delete("/knowledge-bases/{kb_id}")
    def delete_knowledge_base(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        service = knowledge_service_provider()
        repo = service.repository

        # 用户隔离：验证知识库存在且属于当前用户
        kb = repo.get_knowledge_base(kb_id, user_id=user.id)
        if kb is None:
            raise HTTPException(status_code=404, detail="Knowledge base not found.")

        # Delete database records (cascades to documents, chunks, tasks, index_versions)
        if not hasattr(repo, "delete_knowledge_base") or not repo.delete_knowledge_base(kb_id):
            raise HTTPException(status_code=500, detail="Failed to delete knowledge base from database.")

        # Delete FAISS index files
        settings = settings_provider()
        faiss_dir = settings.index_dir / "faiss" / _safe_id(kb_id)
        if faiss_dir.exists():
            shutil.rmtree(faiss_dir, ignore_errors=True)

        # Delete index version directories
        versions_dir = settings.index_dir / "versions"
        if versions_dir.exists():
            for version_dir in versions_dir.iterdir():
                if version_dir.is_dir():
                    # Check if this version belongs to the deleted kb
                    manifest = version_dir / "manifest.json"
                    if manifest.exists():
                        try:
                            import json
                            data = json.loads(manifest.read_text(encoding="utf-8"))
                            if data.get("kb_id") == kb_id:
                                shutil.rmtree(version_dir, ignore_errors=True)
                        except Exception:
                            pass

        service.refresh_global_indexes()
        clear_chat_cache()
        return {"deleted": True, "kb_id": kb_id}

    @router.post("/knowledge-bases/{kb_id}/rebuild")
    def rebuild_knowledge_base(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        get_user_kb(knowledge_service_provider(), kb_id, user.id)
        return {"message": "Knowledge base rebuild submitted.", **submit_ingestion(kb_id, build_index=True, force=True)}

    @router.post("/knowledge-bases/{kb_id}/rebuild-graph")
    def rebuild_knowledge_graph(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        get_user_kb(knowledge_service_provider(), kb_id, user.id)
        raise HTTPException(
            status_code=501,
            detail="Knowledge graph rebuild is not implemented in this version.",
        )

    @router.post("/knowledge-bases/{kb_id}/rebuild-vectors")
    def rebuild_vector_index(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        get_user_kb(knowledge_service_provider(), kb_id, user.id)
        info = knowledge_service_provider().build_indexes(kb_id=kb_id)
        clear_chat_cache()
        return {"message": "Index rebuilt.", **info}

    @router.post("/knowledge-bases/{kb_id}/cleanup")
    def cleanup_knowledge_base(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        get_user_kb(knowledge_service_provider(), kb_id, user.id)
        raise HTTPException(
            status_code=501,
            detail="Knowledge base cleanup is not implemented in this version.",
        )

    @router.get("/knowledge-bases/{kb_id}/stats")
    @router.get("/knowledge-bases/{kb_id}/statistics")
    def knowledge_base_stats(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:

        kb = get_user_kb(knowledge_service_provider(), kb_id, user.id)
        docs = knowledge_service_provider().list_documents(kb_id, limit=10000)
        active = knowledge_service_provider().get_active_index_version(kb_id=kb_id)
        return {
            "initialized": bool(active and active.kb_id == kb_id),
            "document_count": len(docs),
            "total_chunks": sum(doc.chunk_count for doc in docs),
            "chunks": sum(doc.chunk_count for doc in docs),
            "entity_count": 0,
            "relation_count": 0,
            "graph_source": "none",
            "graph_backend_status": "not_implemented",
            "last_error": None,
            "configured_models": {"best": settings_provider().qwen_model, "cheap": "qwen-turbo"},
        }

    @router.get("/knowledge-bases/{kb_id}/graph")
    def knowledge_base_graph(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:

        get_user_kb(knowledge_service_provider(), kb_id, user.id)
        return {
            "nodes": [],
            "edges": [],
            "stats": {"node_count": 0, "edge_count": 0},
            "source": "none",
            "graph_backend_status": "not_implemented",
            "message": "Knowledge graph is not implemented yet.",
            "last_error": None,
        }

    @router.get("/documents/")
    def list_documents(
        kb_id: str | None = None,
        limit: int = Query(default=500, ge=1, le=2000),
        user: User = Depends(current_user),
    ) -> list[dict[str, Any]]:
        # 所属权检查：只返回用户自己的知识库中的文档
        if kb_id:
            get_user_kb(knowledge_service_provider(), kb_id, user.id)
            docs = knowledge_service_provider().list_documents(kb_id, limit=limit)
        else:
            user_kbs = knowledge_service_provider().list_knowledge_bases(user_id=user.id, limit=1000)
            docs = []
            remaining = limit
            for kb in user_kbs:
                if remaining <= 0:
                    break
                batch = knowledge_service_provider().list_documents(kb.kb_id, limit=remaining)
                docs.extend(batch)
                remaining = limit - len(docs)
        return [_document_payload(doc) for doc in docs]

    @router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
    async def upload_document(
        kb_id: str = Form(...),
        file: UploadFile = File(...),
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        # 所属权检查：只能上传到自己的知识库
        settings = settings_provider()
        get_user_kb(knowledge_service_provider(), kb_id, user.id)
        if not file.filename:
            raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
        try:
            validate_upload_filename(file.filename, settings.upload_allowed_extensions)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            payload_bytes = await read_upload_limited(file, settings.upload_max_bytes)
        except UploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        upload_dir = settings.object_storage_root / "uploads" / kb_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
        target = upload_dir / safe_name
        target.write_bytes(payload_bytes)
        try:
            doc = knowledge_service_provider().register_local_document(
                kb_id=kb_id,
                path=target,
                title=Path(file.filename).stem,
                metadata={"uploaded_filename": file.filename, "owner_id": user.id},
            )
            submit_ingestion(kb_id, build_index=True, document_ids=[doc.document_id])
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _document_payload(doc)

    @router.delete("/documents/{document_id}")
    def delete_document(document_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        service = knowledge_service_provider()
        repo = service.repository
        if not hasattr(repo, "delete_document"):
            raise HTTPException(status_code=501, detail="Document deletion is not supported by this repository.")
        doc = repo.get_document(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        get_user_kb(service, doc.kb_id, user.id)

        deleted = repo.delete_document(document_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        # Delete physical file
        service._resolve_document_path(deleted.path).unlink(missing_ok=True)

        # Rebuild indexes from remaining DB chunks without re-parsing documents.
        try:
            service.build_indexes(kb_id=deleted.kb_id, force_vector_rebuild=True)
        except ValueError:
            service.refresh_global_indexes()

        clear_chat_cache()
        return {"deleted": True, "document_id": document_id, "kb_id": deleted.kb_id}

    @router.post("/documents/{document_id}/reprocess")
    def reprocess_document(document_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        repo = knowledge_service_provider().repository
        doc = repo.get_document(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        # 所属权检查
        get_user_kb(knowledge_service_provider(), doc.kb_id, user.id)
        return {"message": "Document reprocess submitted.", **submit_ingestion(doc.kb_id, build_index=True, document_ids=[doc.document_id], force=True)}

    @router.get("/documents/{document_id}/progress")
    def document_progress(document_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        doc = knowledge_service_provider().repository.get_document(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        get_user_kb(knowledge_service_provider(), doc.kb_id, user.id)
        progress_map = {
            "registered": 5,
            "parsing": 25,
            "chunked": 65,
            "indexed": 100,
            "failed": 100,
        }
        return {
            "document_id": doc.document_id,
            "status": _document_status_for_frontend(doc.status),
            "raw_status": doc.status,
            "progress": progress_map.get(doc.status, 10),
            "progress_stage": doc.status,
            "error_message": doc.error,
        }

    @router.post("/query/stream")
    def query_stream(payload: QueryRequest, user: User = Depends(current_user)) -> StreamingResponse:
        question = payload.question.strip()
        service = knowledge_service_provider()

        try:
            kb_id, kb_ids = resolve_query_kb_scope(
                knowledge_base_id=payload.knowledge_base_id,
                kb_ids=payload.kb_ids,
                user_id=user.id,
                get_knowledge_base=lambda kid, uid: service.get_knowledge_base(kid, user_id=uid),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        conversation_id = None if payload.session_id in (None, "") else str(payload.session_id)
        if conversation_id:
            chat = chat_service_provider()
            if chat.repository.get_conversation(conversation_id, user_id=user.id) is None:
                raise HTTPException(status_code=404, detail="Session not found.")

        llm_model = _resolve_llm_model(payload, user.id)

        def event_stream():
            started = perf_counter()
            try:
                with user_api_key_scope(settings_provider().database_url, user.id, provider=payload.llm_provider):
                    chat = chat_service_provider()
                    if not conversation_id:
                        conversation = chat.create_conversation(
                            title=question[:80] or "New conversation",
                            metadata={
                                "knowledge_base_id": kb_id or "",
                                "kb_ids": kb_ids or [],
                                "mode": payload.mode,
                            },
                            user_id=user.id,
                        )
                        active_conversation_id = conversation.conversation_id
                    else:
                        active_conversation_id = conversation_id

                    response = None
                    for event in chat.ask_stream(
                        question,
                        conversation_id=active_conversation_id,
                        user_id=user.id,
                        kb_id=kb_id or None,
                        kb_ids=kb_ids,
                        use_memory=payload.use_memory,
                        mode=payload.mode,
                        top_k=payload.top_k,
                        memory_turn_window=payload.memory_turn_window,
                        llm_model=llm_model,
                    ):
                        if event.status:
                            yield _sse_data({"status": event.status})
                        if event.content:
                            yield _sse_data({"content": event.content})
                        if event.done and event.result is not None and event.chat is not None:
                            response = event.chat

                    if response is None:
                        raise RuntimeError("Stream ended without a final answer.")

                    answer = response.result.answer
                    sources = [_source_payload(item) for item in response.result.evidence[: payload.top_k]]
                    yield _sse_data(
                        {
                            "done": True,
                            "answer": answer,
                            "tokens": response.result.token_usage.total_tokens,
                            "mode": payload.mode,
                            "session_id": response.conversation.conversation_id,
                            "query_time": round(perf_counter() - started, 3),
                            "metadata": {
                                "memory": {
                                    "used": payload.use_memory,
                                    "message_count": len(chat.list_messages(active_conversation_id)),
                                },
                                "retrieval": {
                                    "top_k": payload.top_k,
                                    "source_count": len(sources),
                                    "index_version": response.result.metadata.get("index_version"),
                                    "knowledge_base_id": kb_id or "",
                                    "kb_ids": kb_ids or [],
                                },
                                "agent": {
                                    "route": response.result.metadata.get("route", {}),
                                    "plan": response.result.metadata.get("plan", {}),
                                    "strategy": response.result.metadata.get("strategy", ""),
                                    "risk_flags": response.result.metadata.get("risk_flags", []),
                                    "gated": response.result.metadata.get("gated", False),
                                    "citations": response.result.metadata.get("citations", []),
                                    "trace": response.result.metadata.get("trace", {}),
                                },
                            },
                            "sources": sources,
                        }
                    )
            except Exception as exc:
                yield _sse_data({"done": True, "error": str(exc), "status_code": 500})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @router.get("/query/sessions")
    def list_conversation_sessions(
        limit: int = Query(default=50, ge=1, le=200),
        user: User = Depends(current_user),
    ) -> list[dict[str, Any]]:
        # 用户隔离：只返回当前用户的会话列表
        chat = chat_service_provider()
        return [_session_summary(chat, conversation) for conversation in chat.list_conversations(limit=limit, user_id=user.id)]

    @router.get("/query/sessions/{session_id}")
    def get_conversation_session(session_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        # 用户隔离：只允许访问自己的会话
        chat = chat_service_provider()
        conversation = chat.repository.get_conversation(session_id, user_id=user.id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation session not found.")
        return {"session": _session_summary(chat, conversation), "turns": _turns_from_messages(chat.list_messages(session_id))}

    @router.delete("/query/sessions/{session_id}")
    def delete_conversation_session(session_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        # 用户隔离：先验证会话属于当前用户
        chat = chat_service_provider()
        conversation = chat.repository.get_conversation(session_id, user_id=user.id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation session not found.")
        deleted = chat.repository.delete_conversation(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Conversation session not found.")
        return {"deleted": True, "session_id": session_id}

    @router.get("/test-sets")
    def list_test_sets(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        return evaluation_repository().list_test_sets(owner_id=user.id)

    @router.post("/test-sets/upload", status_code=status.HTTP_201_CREATED)
    async def upload_test_set(file: UploadFile = File(...), user: User = Depends(current_user)) -> dict[str, Any]:
        settings = settings_provider()
        if not file.filename:
            raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
        try:
            validate_upload_filename(file.filename, settings.upload_allowed_extensions)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            payload_bytes = await read_upload_limited(file, settings.upload_max_bytes)
        except UploadTooLargeError as exc:
            raise HTTPException(status_code=413, detail=str(exc)) from exc
        test_set_id = f"ts_{uuid.uuid4().hex[:8]}"
        upload_dir = settings.object_storage_root / "evaluation" / "test_sets"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{test_set_id}_{Path(file.filename).name}"
        target.write_bytes(payload_bytes)
        try:
            test_set = load_test_set(target, test_set_id=test_set_id, name=Path(file.filename).stem)
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        test_set.created_at = now_iso()
        repo = evaluation_repository()
        repo.save_test_set(test_set, file_path=str(target), owner_id=user.id)
        created = repo.get_test_set(test_set_id, owner_id=user.id)
        if created is None:
            raise HTTPException(status_code=500, detail="Test set was saved but cannot be loaded.")
        return created

    @router.delete("/test-sets/{test_set_id}")
    def delete_test_set(test_set_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        repo = evaluation_repository()
        record = repo.get_test_set_record(test_set_id, owner_id=user.id)
        if record is None:
            raise HTTPException(status_code=404, detail="Test set not found.")
        repo.delete_test_set(test_set_id, owner_id=user.id)
        Path(str(record.get("file_path") or "")).unlink(missing_ok=True)
        return {"deleted": True, "test_set_id": test_set_id}

    @router.get("/evaluations")
    def list_evaluations(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        return evaluation_repository().list_reports(owner_id=user.id)

    @router.post("/evaluations", status_code=status.HTTP_201_CREATED)
    def create_evaluation(payload: CreateEvaluationRequest, user: User = Depends(current_user)) -> dict[str, Any]:
        repo = evaluation_repository()
        test_set_record = repo.get_test_set_record(payload.test_set_id, owner_id=user.id)
        if test_set_record is None:
            raise HTTPException(status_code=404, detail="Test set not found.")
        kb = get_user_kb(knowledge_service_provider(), payload.kb_id, user.id)
        report_id = f"eval_{uuid.uuid4().hex[:8]}"
        report = EvalReport(
            id=report_id,
            kb_id=payload.kb_id,
            kb_name=kb.name,
            test_set_id=payload.test_set_id,
            test_set_name=str(test_set_record["name"]),
            strategy=payload.strategy.value,
            top_k=payload.top_k,
            status="running",
            progress_total=int(test_set_record.get("count") or 0),
            created_at=now_iso(),
        )
        repo.create_report(report, owner_id=user.id)

        def worker() -> None:
            with user_api_key_scope(settings_provider().database_url, user.id, provider="dashscope"):
                test_set = load_test_set(
                    str(test_set_record["file_path"]),
                    test_set_id=payload.test_set_id,
                    name=str(test_set_record["name"]),
                )

                def progress(current: int, total: int) -> None:
                    existing = repo.get_report(report_id, owner_id=user.id)
                    if existing:
                        existing.progress_current = current
                        existing.progress_total = total
                        repo.update_report(existing, owner_id=user.id)

                result = run_retrieval_evaluation(
                    pipeline=chat_service_provider().pipeline,
                    config=EvalConfig(
                        kb_id=payload.kb_id,
                        test_set_id=payload.test_set_id,
                        strategy=payload.strategy,
                        top_k=payload.top_k,
                    ),
                    test_set=test_set,
                    kb_name=kb.name,
                    progress_callback=progress,
                )
                result.id = report_id
                repo.update_report(result, owner_id=user.id)

        executor.submit(report_id, worker)
        return {"id": report_id, "status": "running"}

    @router.get("/evaluations/{evaluation_id}")
    def get_evaluation(evaluation_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        report = evaluation_repository().get_report(evaluation_id, owner_id=user.id)
        if report is None:
            raise HTTPException(status_code=404, detail="Evaluation not found.")
        return report.model_dump()

    @router.delete("/evaluations/{evaluation_id}")
    def delete_evaluation(evaluation_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        if not evaluation_repository().delete_report(evaluation_id, owner_id=user.id):
            raise HTTPException(status_code=404, detail="Evaluation not found.")
        return {"deleted": True, "evaluation_id": evaluation_id}

    @router.get("/evaluations/{evaluation_id}/compare/{other_evaluation_id}")
    def compare_evaluations(evaluation_id: str, other_evaluation_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        repo = evaluation_repository()
        first = repo.get_report(evaluation_id, owner_id=user.id)
        second = repo.get_report(other_evaluation_id, owner_id=user.id)
        if first is None or second is None:
            raise HTTPException(status_code=404, detail="Evaluation not found.")
        return {"eval_1": first.model_dump(), "eval_2": second.model_dump()}

    return router


class AuthService:
    def __init__(self, settings_provider: Callable[[], Settings]) -> None:
        self.settings_provider = settings_provider
        self.database_url = settings_provider().database_url

    def sessionmaker(self):
        return get_sync_sessionmaker(self.database_url)

    def register(self, payload: RegisterRequest) -> dict[str, Any]:
        with self.sessionmaker()() as session:
            session.execute(select(User).with_for_update())
            existing = session.scalar(
                select(User).where(
                    or_(
                        User.email == payload.email,
                        User.display_name == payload.username,
                        User.display_name == (payload.full_name or payload.username),
                    )
                )
            )
            if existing is not None:
                raise HTTPException(status_code=400, detail="Username or email already exists.")
            is_first = session.scalar(select(func.count()).select_from(User)) == 0
            user = User(
                email=payload.email,
                display_name=payload.username,
                password_hash=_hash_password(payload.password),
                role="admin" if is_first else "user",
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return self.serialize_user(user)

    def login(self, username: str, password: str) -> dict[str, str]:
        with self.sessionmaker()() as session:
            user = session.scalar(select(User).where(or_(User.email == username, User.display_name == username)))
            if self._matches_default_user(username, password):
                user = self._ensure_default_admin(session, user)
            if user is None or not user.password_hash or not _verify_password(password, user.password_hash):
                raise HTTPException(status_code=401, detail="Invalid username or password.")
            if not user.is_active:
                raise HTTPException(status_code=400, detail="User is inactive.")
            return {"access_token": self._create_token(user.id), "token_type": "bearer"}

    def current_user(self, credentials: HTTPAuthorizationCredentials | None) -> User:
        if credentials is None:
            raise HTTPException(status_code=401, detail="Missing authentication token.")
        try:
            payload = jwt.decode(credentials.credentials, self._secret(), algorithms=["HS256"])
            user_id = str(payload["sub"])
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Invalid authentication token.") from exc
        with self.sessionmaker()() as session:
            user = session.get(User, user_id)
            if user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="User not found or inactive.")
            session.expunge(user)
            return user

    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        with self.sessionmaker()() as session:
            current = session.get(User, user.id)
            if current is None or not current.password_hash:
                raise HTTPException(status_code=404, detail="User not found.")
            if not _verify_password(old_password, current.password_hash):
                raise HTTPException(status_code=400, detail="Current password is incorrect.")
            current.password_hash = _hash_password(new_password)
            session.commit()

    def serialize_user(self, user: User) -> dict[str, Any]:
        return {
            "id": user.id,
            "username": user.display_name or user.email.split("@", 1)[0],
            "email": user.email,
            "full_name": user.display_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": _datetime_to_iso(user.created_at),
        }

    def _create_token(self, user_id: str) -> str:
        expires = datetime.now(UTC) + timedelta(days=7)
        return jwt.encode({"sub": user_id, "exp": expires}, self._secret(), algorithm="HS256")

    def _secret(self) -> str:
        secret = os.getenv("FINLONGRAG_SECRET_KEY") or os.getenv("SECRET_KEY")
        if secret:
            return secret
        env = os.getenv("FINLONGRAG_ENV", "development").strip().lower()
        if env in {"production", "prod"}:
            raise RuntimeError("FINLONGRAG_SECRET_KEY must be set in production")
        return "finlongrag-dev-secret"

    def _matches_default_user(self, username: str, password: str) -> bool:
        return username == os.getenv("FINLONGRAG_DEFAULT_USERNAME", "admin") and password == os.getenv(
            "FINLONGRAG_DEFAULT_PASSWORD", "finlongrag"
        )

    def _ensure_default_admin(self, session, user: User | None) -> User:
        default_email = os.getenv("FINLONGRAG_DEFAULT_EMAIL", "admin@finlongrag.local")
        default_username = os.getenv("FINLONGRAG_DEFAULT_USERNAME", "admin")
        default_password = os.getenv("FINLONGRAG_DEFAULT_PASSWORD", "finlongrag")
        default_user = user or session.scalar(
            select(User).where(or_(User.email == default_email, User.display_name == default_username))
        )
        if default_user is None:
            default_user = User(
                email=default_email,
                display_name=default_username,
                password_hash=_hash_password(default_password),
                role="admin",
                is_active=True,
            )
            session.add(default_user)
            session.commit()
            session.refresh(default_user)
        return default_user

    @staticmethod
    def _is_first_user(session) -> bool:
        return session.scalar(select(User).limit(1)) is None


def _kb_payload(kb, service: KnowledgeService) -> dict[str, Any]:
    docs = service.list_documents(kb.kb_id, limit=10000)
    active = service.get_active_index_version(kb_id=kb.kb_id)
    return {
        "id": kb.kb_id,
        "kb_id": kb.kb_id,
        "name": kb.name,
        "description": kb.description,
        "owner_id": kb.metadata.get("owner_id", ""),
        "enable_local": bool(kb.metadata.get("enable_local", True)),
        "enable_naive_rag": bool(kb.metadata.get("enable_naive_rag", True)),
        "enable_bm25": bool(kb.metadata.get("enable_bm25", True)),
        "document_count": len(docs),
        "total_chunks": sum(doc.chunk_count for doc in docs),
        "is_initialized": bool(active and active.kb_id == kb.kb_id),
        "status": kb.status,
        "created_at": _unix_to_iso(kb.created_at),
        "updated_at": _unix_to_iso(kb.updated_at),
        "entity_count": 0,
    }


def _document_payload(doc: KnowledgeDocumentRecord) -> dict[str, Any]:
    return {
        "id": doc.document_id,
        "document_id": doc.document_id,
        "knowledge_base_id": doc.kb_id,
        "kb_id": doc.kb_id,
        "doc_id": doc.doc_id,
        "filename": doc.metadata.get("uploaded_filename") or Path(doc.path).name,
        "title": doc.title,
        "path": doc.path,
        "domain": doc.domain,
        "status": _document_status_for_frontend(doc.status),
        "raw_status": doc.status,
        "file_size": doc.metadata.get("file_size", 0),
        "page_count": doc.page_count,
        "chunk_count": doc.chunk_count,
        "error_message": doc.error,
        "created_at": _unix_to_iso(doc.created_at),
        "updated_at": _unix_to_iso(doc.updated_at),
        "progress": {"registered": 5, "parsing": 25, "chunked": 65, "indexed": 100, "failed": 100}.get(doc.status, 10),
        "progress_stage": doc.status,
    }


def _document_status_for_frontend(status: str) -> str:
    normalized = str(status or "").lower()
    if normalized == "indexed":
        return "completed"
    if normalized in {"parsing", "chunked"}:
        return "processing"
    if normalized == "registered":
        return "pending"
    if normalized == "failed":
        return "failed"
    return normalized or "pending"


def _session_summary(chat: ChatService, conversation) -> dict[str, Any]:
    messages = chat.list_messages(conversation.conversation_id, limit=1000)
    kb_id = conversation.metadata.get("knowledge_base_id") or _last_kb_id(messages)
    kb_ids = conversation.metadata.get("kb_ids") or _last_kb_ids(messages)
    return {
        "id": conversation.conversation_id,
        "title": conversation.title,
        "knowledge_base_id": kb_id,
        "kb_ids": [str(kid) for kid in kb_ids if kid],
        "created_at": _unix_to_iso(conversation.created_at),
        "updated_at": _unix_to_iso(conversation.updated_at),
        "last_active_at": _unix_to_iso(conversation.updated_at),
        "turn_count": len([msg for msg in messages if msg.role == "user"]),
    }


def _turns_from_messages(messages) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    pending_user = None
    for message in messages:
        if message.role == "user":
            pending_user = message
            continue
        if message.role != "assistant" or pending_user is None:
            continue
        metadata = message.metadata or {}
        evidence = metadata.get("evidence") or []
        turns.append(
            {
                "id": message.message_id,
                "turn_index": len(turns) + 1,
                "question": pending_user.content,
                "answer": message.content,
                "requested_mode": pending_user.metadata.get("mode", "auto"),
                "mode": metadata.get("mode", pending_user.metadata.get("mode", "auto")),
                "response_time": metadata.get("latency_ms"),
                "token_count": (metadata.get("token_usage") or {}).get("total_tokens", 0),
                "sources": [_source_payload_from_dict(item) for item in evidence],
                "memory": metadata.get("memory", {}),
                "created_at": _unix_to_iso(message.created_at),
                # Agent traceability fields — available on session replay
                "agent": {
                    "route": metadata.get("route", {}),
                    "strategy": metadata.get("strategy", ""),
                    "plan": metadata.get("plan", {}),
                    "gated": metadata.get("gated", False),
                    "citations": metadata.get("citations", []),
                    "risk_flags": metadata.get("risk_flags", []),
                },
            }
        )
        pending_user = None
    return turns


def _source_payload(item) -> dict[str, Any]:
    return _source_payload_from_dict(item.to_dict() if hasattr(item, "to_dict") else asdict(item))


def _source_payload_from_dict(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    return {
        "chunk_id": item.get("chunk_id", ""),
        "doc_id": item.get("doc_id", ""),
        "title": metadata.get("title") or item.get("doc_id", ""),
        "source": item.get("source", ""),
        "score": item.get("score", 0.0),
        "page": metadata.get("page") or item.get("page"),
        "text": item.get("evidence_text", ""),
        "content": item.get("evidence_text", ""),
        "metadata": metadata,
    }


def _last_kb_id(messages) -> str:
    for message in reversed(messages):
        kb_id = (message.metadata or {}).get("knowledge_base_id")
        if kb_id:
            return str(kb_id)
    return ""


def _last_kb_ids(messages) -> list[str]:
    for message in reversed(messages):
        kb_ids = (message.metadata or {}).get("kb_ids") or []
        if kb_ids:
            return [str(kid) for kid in kb_ids if kid]
    return []


def _sse_data(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 200_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt, digest = stored.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), 200_000).hex()
    return hmac.compare_digest(candidate, digest)


def _initial_api_keys() -> dict[str, dict[str, Any]]:
    key = get_api_key()
    if not key:
        return {}
    return {
        "env-dashscope": {
            "id": "env-dashscope",
            "provider": "dashscope",
            "description": "Environment DashScope key",
            "model_name": None,
            "key_preview": _mask_key(key),
            "created_at": now_iso(),
        }
    }


def _mask_key(value: str) -> str:
    if len(value) <= 10:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def _unix_to_iso(value: float) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(float(value), UTC).isoformat()


def _datetime_to_iso(value: datetime | None) -> str:
    return value.isoformat() if value else ""
