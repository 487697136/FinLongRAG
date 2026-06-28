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
from typing import Any

import jwt
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from finlongrag.conversation.service import ChatService
from finlongrag.core.config import Settings, get_api_key
from finlongrag.db import get_sync_sessionmaker
from finlongrag.db.models.user import User
from finlongrag.evaluation_center.loader import load_test_set
from finlongrag.evaluation_center.repository import EvaluationRepository, now_iso
from finlongrag.evaluation_center.runner import run_retrieval_evaluation
from finlongrag.evaluation_center.schemas import EvalConfig, EvalReport, RetrievalStrategy
from finlongrag.knowledge.service import KnowledgeService
from finlongrag.storage.knowledge_repository import KnowledgeDocumentRecord
from finlongrag.tasks.local import get_default_executor

security = HTTPBearer(auto_error=False)


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
    mode: str = "auto"
    top_k: int = 20
    use_memory: bool = True
    memory_turn_window: int = 4
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
    api_keys: dict[str, dict[str, Any]] = _initial_api_keys()

    def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> User:
        return auth.current_user(credentials)

    def evaluation_repository() -> EvaluationRepository:
        return EvaluationRepository(settings_provider().database_url)

    def run_ingestion_task(task_id: str, *, build_index: bool) -> None:
        task = knowledge_service_provider().run_ingestion_task(task_id, raise_on_error=False)
        if build_index and task.status == "succeeded":
            clear_chat_cache()

    def submit_ingestion(kb_id: str, *, build_index: bool = True) -> dict[str, Any]:
        task = knowledge_service_provider().create_ingestion_task(
            kb_id,
            build_index=build_index,
            status="queued",
            stage="queued",
            metadata={"execution_mode": "local_thread"},
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

    @router.get("/api-keys/")
    def list_api_keys(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        _ = user
        return [dict(item, api_key="") for item in api_keys.values()]

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

    @router.post("/api-keys/")
    def save_api_key(payload: ApiKeySaveRequest, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        key_id = uuid.uuid4().hex
        api_keys[key_id] = {
            "id": key_id,
            "provider": payload.provider,
            "description": payload.description or payload.provider,
            "model_name": payload.model_name,
            "key_preview": _mask_key(payload.api_key),
            "created_at": now_iso(),
        }
        if payload.provider.startswith("dashscope"):
            os.environ["DASHSCOPE_API_KEY"] = payload.api_key
        return dict(api_keys[key_id], api_key="")

    @router.delete("/api-keys/{key_id}")
    def delete_api_key(key_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        if key_id.startswith("env-"):
            raise HTTPException(status_code=400, detail="Environment-provided keys cannot be deleted here.")
        api_keys.pop(key_id, None)
        return {"deleted": True}

    @router.get("/api-keys/runtime-status")
    def runtime_status(user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        settings = settings_provider()
        return {
            "app": {"name": "FinLongRAG", "version": "0.1.0", "dry_run": dry_run},
            "database_url": _redact_database_url(settings.database_url),
            "graph_backend_requested": "postgresql_jsonb",
            "neo4j": {"configured": False, "connected": False, "url": ""},
            "upload": {
                "max_upload_size": 100 * 1024 * 1024,
                "allowed_extensions": [".pdf", ".txt", ".md", ".docx", ".xlsx", ".csv"],
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
        faiss_dir = settings.index_dir / "faiss" / kb_id
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

        clear_chat_cache()
        return {"deleted": True, "kb_id": kb_id}

    @router.post("/knowledge-bases/{kb_id}/rebuild")
    def rebuild_knowledge_base(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:

        return {"message": "Knowledge base rebuild submitted.", **submit_ingestion(kb_id, build_index=True)}

    @router.post("/knowledge-bases/{kb_id}/rebuild-graph")
    def rebuild_knowledge_graph(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:

        knowledge_service_provider().get_knowledge_base(kb_id, user_id=user.id)
        return {"message": "Graph rebuild is not enabled in the first integrated version.", "status": "skipped"}

    @router.post("/knowledge-bases/{kb_id}/rebuild-vectors")
    def rebuild_vector_index(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:

        info = knowledge_service_provider().build_indexes(kb_id=kb_id)
        clear_chat_cache()
        return {"message": "Index rebuilt.", **info}

    @router.post("/knowledge-bases/{kb_id}/cleanup")
    def cleanup_knowledge_base(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:

        knowledge_service_provider().get_knowledge_base(kb_id, user_id=user.id)
        return {"message": "Cleanup is not destructive in this version.", "status": "skipped"}

    @router.get("/knowledge-bases/{kb_id}/stats")
    @router.get("/knowledge-bases/{kb_id}/statistics")
    def knowledge_base_stats(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:

        kb = knowledge_service_provider().get_knowledge_base(kb_id, user_id=user.id)
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
            "graph_backend_status": "ready" if kb else "error",
            "last_error": None,
            "configured_models": {"best": settings_provider().qwen_model, "cheap": "qwen-turbo"},
        }

    @router.get("/knowledge-bases/{kb_id}/graph")
    def knowledge_base_graph(kb_id: str, user: User = Depends(current_user)) -> dict[str, Any]:

        knowledge_service_provider().get_knowledge_base(kb_id, user_id=user.id)
        return {
            "nodes": [],
            "edges": [],
            "stats": {"node_count": 0, "edge_count": 0},
            "source": "none",
            "graph_backend_status": "ready",
            "message": "Knowledge graph is reserved for the next implementation phase.",
            "last_error": None,
        }

    @router.get("/documents/")
    def list_documents(
        kb_id: str | None = None,
        limit: int = Query(default=500, ge=1, le=2000),
        user: User = Depends(current_user),
    ) -> list[dict[str, Any]]:
        _ = user
        docs = knowledge_service_provider().list_documents(kb_id, limit=limit)
        return [_document_payload(doc) for doc in docs]

    @router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
    async def upload_document(
        kb_id: str = Form(...),
        file: UploadFile = File(...),
        user: User = Depends(current_user),
    ) -> dict[str, Any]:
        _ = user
        if not file.filename:
            raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
        upload_dir = settings_provider().object_storage_root / "uploads" / kb_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex}_{Path(file.filename).name}"
        target = upload_dir / safe_name
        with target.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            doc = knowledge_service_provider().register_local_document(
                kb_id=kb_id,
                path=target,
                title=Path(file.filename).stem,
                metadata={"uploaded_filename": file.filename, "owner_id": user.id},
            )
            submit_ingestion(kb_id, build_index=True)
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _document_payload(doc)

    @router.delete("/documents/{document_id}")
    def delete_document(document_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        repo = knowledge_service_provider().repository
        if not hasattr(repo, "delete_document"):
            raise HTTPException(status_code=501, detail="Document deletion is not supported by this repository.")
        deleted = repo.delete_document(document_id)
        if deleted is None:
            raise HTTPException(status_code=404, detail="Document not found.")

        # Delete physical file
        Path(deleted.path).unlink(missing_ok=True)

        # Trigger index rebuild for the knowledge base
        submit_ingestion(deleted.kb_id, build_index=True)

        clear_chat_cache()
        return {"deleted": True, "document_id": document_id, "kb_id": deleted.kb_id}

    @router.post("/documents/{document_id}/reprocess")
    def reprocess_document(document_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        repo = knowledge_service_provider().repository
        doc = repo.get_document(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return {"message": "Document reprocess submitted.", **submit_ingestion(doc.kb_id, build_index=True)}

    @router.get("/documents/{document_id}/progress")
    def document_progress(document_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        doc = knowledge_service_provider().repository.get_document(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found.")
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

        # 处理单 KB 或多 KB 模式
        kb_id = None
        kb_ids = None
        if payload.kb_ids:
            # 多知识库融合模式
            kb_ids = [str(kid) for kid in payload.kb_ids if kid]
            kb_id = kb_ids[0] if kb_ids else ""  # 用于 conversation metadata
        elif payload.knowledge_base_id:
            # 单知识库隔离模式
            kb_id = str(payload.knowledge_base_id)

        def event_stream():
            started = perf_counter()
            try:
                chat = chat_service_provider()
                conversation_id = None if payload.session_id in (None, "") else str(payload.session_id)
                if not conversation_id:
                    # 用户隔离：创建会话时设置 user_id
                    conversation = chat.create_conversation(
                        title=question[:80] or "New conversation",
                        metadata={
                            "knowledge_base_id": kb_id or "",
                            "kb_ids": kb_ids or [],
                            "mode": payload.mode
                        },
                        user_id=user.id,
                    )
                    conversation_id = conversation.conversation_id

                # 传递 kb_ids（多库）或 kb_id（单库）
                response = chat.ask(
                    question,
                    conversation_id=conversation_id,
                    kb_id=kb_id or None,
                    kb_ids=kb_ids
                )

                answer = response.result.answer
                # 流式输出：更小的块 + 适当延迟，提升用户体验
                for chunk in _chunks(answer, size=8):  # 从 28 改为 8，更小的块
                    yield _sse_data({"content": chunk})
                    # 短暂延迟模拟流式输出（避免一次性蹦出）
                    import time
                    time.sleep(0.01)  # 10ms 延迟
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
                            "memory": {"used": payload.use_memory, "message_count": len(chat.list_messages(conversation_id))},
                            "retrieval": {
                                "top_k": payload.top_k,
                                "source_count": len(sources),
                                "index_version": response.result.metadata.get("index_version"),
                                "knowledge_base_id": kb_id or "",
                                "kb_ids": kb_ids or [],
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
        _ = user
        return evaluation_repository().list_test_sets()

    @router.post("/test-sets/upload", status_code=status.HTTP_201_CREATED)
    async def upload_test_set(file: UploadFile = File(...), user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        if not file.filename:
            raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
        test_set_id = f"ts_{uuid.uuid4().hex[:8]}"
        upload_dir = settings_provider().object_storage_root / "evaluation" / "test_sets"
        upload_dir.mkdir(parents=True, exist_ok=True)
        target = upload_dir / f"{test_set_id}_{Path(file.filename).name}"
        with target.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        try:
            test_set = load_test_set(target, test_set_id=test_set_id, name=Path(file.filename).stem)
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        test_set.created_at = now_iso()
        repo = evaluation_repository()
        repo.save_test_set(test_set, file_path=str(target))
        created = repo.get_test_set(test_set_id)
        if created is None:
            raise HTTPException(status_code=500, detail="Test set was saved but cannot be loaded.")
        return created

    @router.delete("/test-sets/{test_set_id}")
    def delete_test_set(test_set_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        repo = evaluation_repository()
        record = repo.get_test_set_record(test_set_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Test set not found.")
        repo.delete_test_set(test_set_id)
        Path(str(record.get("file_path") or "")).unlink(missing_ok=True)
        return {"deleted": True, "test_set_id": test_set_id}

    @router.get("/evaluations")
    def list_evaluations(user: User = Depends(current_user)) -> list[dict[str, Any]]:
        _ = user
        return evaluation_repository().list_reports()

    @router.post("/evaluations", status_code=status.HTTP_201_CREATED)
    def create_evaluation(payload: CreateEvaluationRequest, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        repo = evaluation_repository()
        test_set_record = repo.get_test_set_record(payload.test_set_id)
        if test_set_record is None:
            raise HTTPException(status_code=404, detail="Test set not found.")
        try:
            kb = knowledge_service_provider().get_knowledge_base(payload.kb_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
        repo.create_report(report)

        def worker() -> None:
            test_set = load_test_set(str(test_set_record["file_path"]), test_set_id=payload.test_set_id, name=str(test_set_record["name"]))

            def progress(current: int, total: int) -> None:
                existing = repo.get_report(report_id)
                if existing:
                    existing.progress_current = current
                    existing.progress_total = total
                    repo.update_report(existing)

            result = run_retrieval_evaluation(
                pipeline=chat_service_provider().pipeline,
                config=EvalConfig(kb_id=payload.kb_id, test_set_id=payload.test_set_id, strategy=payload.strategy, top_k=payload.top_k),
                test_set=test_set,
                kb_name=kb.name,
                progress_callback=progress,
            )
            result.id = report_id
            repo.update_report(result)

        executor.submit(report_id, worker)
        return {"id": report_id, "status": "running"}

    @router.get("/evaluations/{evaluation_id}")
    def get_evaluation(evaluation_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        report = evaluation_repository().get_report(evaluation_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Evaluation not found.")
        return report.model_dump()

    @router.delete("/evaluations/{evaluation_id}")
    def delete_evaluation(evaluation_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        if not evaluation_repository().delete_report(evaluation_id):
            raise HTTPException(status_code=404, detail="Evaluation not found.")
        return {"deleted": True, "evaluation_id": evaluation_id}

    @router.get("/evaluations/{evaluation_id}/compare/{other_evaluation_id}")
    def compare_evaluations(evaluation_id: str, other_evaluation_id: str, user: User = Depends(current_user)) -> dict[str, Any]:
        _ = user
        first = evaluation_repository().get_report(evaluation_id)
        second = evaluation_repository().get_report(other_evaluation_id)
        if first is None or second is None:
            raise HTTPException(status_code=404, detail="Evaluation not found.")
        return {"eval_1": first.model_dump(), "eval_2": second.model_dump()}

    return router


class AuthService:
    def __init__(self, settings_provider: Callable[[], Settings]) -> None:
        self.settings_provider = settings_provider
        self.database_url = settings_provider().database_url
        self.sessionmaker = get_sync_sessionmaker(self.database_url)

    def register(self, payload: RegisterRequest) -> dict[str, Any]:
        with self.sessionmaker() as session:
            existing = session.scalar(
                select(User).where(or_(User.email == payload.email, User.display_name == payload.username))
            )
            if existing is not None:
                raise HTTPException(status_code=400, detail="Username or email already exists.")
            user = User(
                email=payload.email,
                display_name=payload.full_name or payload.username,
                password_hash=_hash_password(payload.password),
                role="admin" if self._is_first_user(session) else "user",
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            return self.serialize_user(user)

    def login(self, username: str, password: str) -> dict[str, str]:
        with self.sessionmaker() as session:
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
        with self.sessionmaker() as session:
            user = session.get(User, user_id)
            if user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="User not found or inactive.")
            session.expunge(user)
            return user

    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        with self.sessionmaker() as session:
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
        return os.getenv("FINLONGRAG_SECRET_KEY") or os.getenv("SECRET_KEY") or "finlongrag-dev-secret"

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
        else:
            default_user.email = default_email
            default_user.display_name = default_username
            default_user.password_hash = _hash_password(default_password)
            default_user.role = "admin"
            default_user.is_active = True
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
    return {
        "id": conversation.conversation_id,
        "title": conversation.title,
        "knowledge_base_id": kb_id,
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


def _sse_data(data: dict[str, Any]) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _chunks(text: str, *, size: int) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)] or [""]


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


def _redact_database_url(database_url: str) -> str:
    return "<configured>"
