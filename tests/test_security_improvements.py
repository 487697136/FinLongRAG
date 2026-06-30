"""Regression tests for security and reliability improvements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from finlongrag.agent.executor import StepContext, StepExecutor
from finlongrag.agent.planner import AgentPlan, AgentStep, AgentPlanner
from finlongrag.agent.query_cache import QueryAnswerCache
from finlongrag.api.helpers import resolve_query_kb_scope
from finlongrag.conversation.service import ChatService
from finlongrag.core.schema import AnswerResult, Question, TokenUsage
from finlongrag.reasoning.pipeline import ReasoningPipeline
from finlongrag.storage.repository import ConversationRecord


def test_query_cache_distinguishes_conversation_history() -> None:
    cache = QueryAnswerCache(max_entries=8, ttl_seconds=3600)
    question = Question(qid="q1", question="营收是多少？", domain="finance", doc_ids=[])
    question.metadata = {"kb_id": "kb-a"}
    result = AnswerResult(
        qid="q1",
        answer="100亿",
        domain="finance",
        answer_format="open",
        confidence=0.9,
        token_usage=TokenUsage(),
    )
    cache.store(question, result, history="")
    _, hit = cache.lookup(question, history="上一轮：净利润 20 亿")
    assert hit is None


def test_query_cache_skips_store_when_history_present() -> None:
    from dataclasses import replace

    from finlongrag.agent.runtime import AgentRuntime
    from finlongrag.core.config import Settings

    runtime = AgentRuntime(replace(Settings.from_file(), query_cache_enabled=True))
    question = Question(qid="q2", question="同比变化？", domain="finance", doc_ids=[])
    result = AnswerResult(
        qid="q2",
        answer="上升",
        domain="finance",
        answer_format="open",
        confidence=0.8,
        token_usage=TokenUsage(),
    )
    runtime.store_cache(question, result, history="已有上下文")
    _, cached = runtime.query_cache.lookup(question, history="已有上下文")
    assert cached is None


def test_executor_stops_after_critical_step_failure() -> None:
    executor = StepExecutor()
    calls: list[str] = []

    def fail_retrieve(ctx: StepContext) -> StepContext:
        calls.append("retrieve")
        raise RuntimeError("retrieval failed")

    def should_not_run(ctx: StepContext) -> StepContext:
        calls.append("generate")
        return ctx

    executor.register("hybrid_retrieve", fail_retrieve)
    executor.register("generate_answer", should_not_run)
    plan = AgentPlan(
        "rag",
        [
            AgentStep("s1", "hybrid_retrieve", "retrieve"),
            AgentStep("s2", "generate_answer", "answer"),
        ],
    )
    ctx = StepContext(question_text="q", route="rag", plan_steps=["hybrid_retrieve", "generate_answer"])
    ctx = executor.run(plan, ctx)
    assert ctx.failed is True
    assert calls == ["retrieve"]


def test_resolve_query_kb_scope_normalizes_single_kb_ids() -> None:
    kb_id, kb_ids = resolve_query_kb_scope(
        knowledge_base_id=None,
        kb_ids=["kb-only"],
        user_id="user-1",
        get_knowledge_base=lambda kid, uid: object(),
    )
    assert kb_id == "kb-only"
    assert kb_ids == ["kb-only"]


def test_chat_service_rejects_foreign_conversation() -> None:
    @dataclass
    class _Repo:
        def get_conversation(self, conversation_id: str, user_id: str | None = None):
            if conversation_id == "owned" and user_id == "u1":
                return ConversationRecord(
                    conversation_id="owned",
                    title="t",
                    summary="",
                    created_at=0.0,
                    updated_at=0.0,
                    metadata={},
                )
            return None

        def create_conversation(self, **kwargs: Any):
            raise AssertionError("should not create conversation for foreign id")

    service = ChatService(pipeline=object(), repository=_Repo())  # type: ignore[arg-type]
    with pytest.raises(KeyError, match="conversation not found"):
        service._ensure_conversation("foreign", "hello", user_id="u1")


def test_encrypt_decrypt_roundtrip() -> None:
    from finlongrag.core.secrets import decrypt_secret, encrypt_secret

    plain = "sk-test-dashscope-key"
    encrypted = encrypt_secret(plain)
    assert encrypted != plain
    assert decrypt_secret(encrypted) == plain
    assert decrypt_secret(__import__("base64").b64encode(plain.encode()).decode()) == plain


def test_get_api_key_prefers_request_scope() -> None:
    import finlongrag.core.api_key_context as api_key_context
    from finlongrag.core.config import get_api_key

    token = api_key_context._request_api_key.set("scoped-key")
    try:
        assert get_api_key() == "scoped-key"
    finally:
        api_key_context._request_api_key.reset(token)


def test_chat_service_records_assistant_error_on_pipeline_failure() -> None:
    @dataclass
    class _Repo:
        messages: list[Any] = None

        def __post_init__(self) -> None:
            self.messages = []

        def get_conversation(self, conversation_id: str, user_id: str | None = None):
            return ConversationRecord(
                conversation_id=conversation_id,
                title="t",
                summary="",
                created_at=0.0,
                updated_at=0.0,
                metadata={},
            )

        def list_messages(self, conversation_id: str, limit: int = 100):
            return list(self.messages)

        def append_message(self, conversation_id: str, role: str, content: str, metadata=None):
            from finlongrag.storage.repository import MessageRecord

            msg = MessageRecord(
                message_id=f"m{len(self.messages)}",
                conversation_id=conversation_id,
                role=role,
                content=content,
                created_at=0.0,
                metadata=metadata or {},
            )
            self.messages.append(msg)
            return msg

        def update_summary(self, conversation_id: str, summary: str) -> None:
            pass

    class _Pipeline:
        def ask(self, *args, **kwargs):
            raise RuntimeError("boom")

    repo = _Repo()
    service = ChatService(pipeline=_Pipeline(), repository=repo)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="boom"):
        service.ask("hello", conversation_id="c1")
    assert len(repo.messages) == 2
    assert repo.messages[1].role == "assistant"
    assert repo.messages[1].metadata.get("failed") is True


def test_structured_route_respects_kb_scope_gate() -> None:
    from dataclasses import replace

    from finlongrag.agent.router import RouteDecision, RouteType
    from finlongrag.core.config import Settings

    settings = replace(Settings.from_file(), require_kb_scope_for_rag=True)
    question = Question(
        qid="mcq-1",
        question="以下哪项正确？",
        domain="finance",
        doc_ids=[],
        options=["A", "B", "C"],
        answer_format="single",
    )
    route = RouteDecision(route=RouteType.STRUCTURED, confidence=0.9, reason="test")
    pipeline = object.__new__(ReasoningPipeline)
    pipeline.settings = settings
    warnings = ReasoningPipeline._kb_scope_warnings(pipeline, question)
    assert warnings == ["kb_scope_missing"]
    plan = AgentPlanner().build(question, route)
    result = ReasoningPipeline._build_scope_warning_result(
        pipeline,
        question,
        route,
        plan,
        {},
        warnings,
    )
    assert result.metadata.get("gated") is True
