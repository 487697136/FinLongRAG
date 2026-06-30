"""Tests for request-scoped LLM model override."""

from __future__ import annotations

from finlongrag.core.config import Settings
from finlongrag.reasoning.llm import llm_model_scope, resolve_chat_model


def test_llm_model_scope_overrides_default_model() -> None:
    settings = Settings.from_file()
    assert resolve_chat_model(settings) == settings.qwen_model

    with llm_model_scope("qwen-turbo"):
        assert resolve_chat_model(settings) == "qwen-turbo"

    assert resolve_chat_model(settings) == settings.qwen_model
