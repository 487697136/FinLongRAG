"""Tests for query KB scope validation."""

from __future__ import annotations

import pytest

from finlongrag.api.helpers import resolve_query_kb_scope


def test_resolve_query_kb_scope_validates_single_kb():
    seen: list[tuple[str, str]] = []

    def get_kb(kb_id: str, user_id: str) -> dict[str, str]:
        seen.append((kb_id, user_id))
        return {"kb_id": kb_id}

    kb_id, kb_ids = resolve_query_kb_scope(
        knowledge_base_id="kb-1",
        kb_ids=None,
        user_id="user-1",
        get_knowledge_base=get_kb,
    )
    assert kb_id == "kb-1"
    assert kb_ids is None
    assert seen == [("kb-1", "user-1")]


def test_resolve_query_kb_scope_validates_all_multi_kb_ids():
    seen: list[str] = []

    def get_kb(kb_id: str, user_id: str) -> dict[str, str]:
        assert user_id == "user-1"
        seen.append(kb_id)
        return {"kb_id": kb_id}

    kb_id, kb_ids = resolve_query_kb_scope(
        knowledge_base_id=None,
        kb_ids=["kb-a", "kb-b"],
        user_id="user-1",
        get_knowledge_base=get_kb,
    )
    assert kb_id == "kb-a"
    assert kb_ids == ["kb-a", "kb-b"]
    assert seen == ["kb-a", "kb-b"]


def test_resolve_query_kb_scope_propagates_missing_kb():
    def get_kb(kb_id: str, user_id: str) -> dict[str, str]:
        raise KeyError(f"knowledge base not found: {kb_id}")

    with pytest.raises(KeyError):
        resolve_query_kb_scope(
            knowledge_base_id="missing",
            kb_ids=None,
            user_id="user-1",
            get_knowledge_base=get_kb,
        )
