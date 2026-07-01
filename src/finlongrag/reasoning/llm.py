"""LLM client boundary."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Protocol

import requests

from finlongrag.core.config import Settings, get_api_key
from finlongrag.core.schema import TokenUsage

_request_llm_model: ContextVar[str | None] = ContextVar("request_llm_model", default=None)


@contextmanager
def llm_model_scope(model: str | None):
    """Temporarily override the chat model for the current request."""
    if not model:
        yield
        return
    token = _request_llm_model.set(model)
    try:
        yield
    finally:
        try:
            _request_llm_model.reset(token)
        except ValueError:
            # Streaming responses may close the generator from a different
            # execution context than the one that created the token.
            pass


def resolve_chat_model(settings: Settings, explicit: str | None = None) -> str:
    return explicit or _request_llm_model.get() or settings.qwen_model


@dataclass
class LLMResponse:
    text: str
    usage: TokenUsage
    raw: dict | None = None


@dataclass
class LLMStreamChunk:
    """Single chunk from streaming response."""
    content: str
    finish_reason: str | None = None


class ChatModel(Protocol):
    def chat(self, messages: list[dict[str, str]], *, max_tokens: int | None = None, temperature: float | None = None) -> LLMResponse:
        ...

    def chat_stream(self, messages: list[dict[str, str]], *, max_tokens: int | None = None, temperature: float | None = None) -> Iterator[LLMStreamChunk]:
        ...


class QwenChatModel:
    """DashScope OpenAI-compatible chat client with deterministic dry-run mode."""

    def __init__(self, settings: Settings, *, dry_run: bool = False) -> None:
        self.settings = settings
        self.dry_run = dry_run
        if not dry_run and not get_api_key():
            raise RuntimeError("Missing API key. Set DASHSCOPE_API_KEY or use dry_run=True.")

    def _api_key(self) -> str:
        key = get_api_key()
        if not key and not self.dry_run:
            raise RuntimeError("Missing API key. Set DASHSCOPE_API_KEY or use dry_run=True.")
        return key or ""

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> LLMResponse:
        if self.dry_run:
            prompt_chars = sum(len(message.get("content", "")) for message in messages)
            text = '{"label":"insufficient","answer":"A","confidence":0.0,"reason":"dry-run"}'
            return LLMResponse(text=text, usage=TokenUsage(prompt_tokens=max(1, prompt_chars // 2), completion_tokens=1))

        url = self.settings.qwen_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": resolve_chat_model(self.settings),
            "messages": messages,
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.answer_max_tokens,
        }
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {self._api_key()}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=self.settings.request_timeout_seconds,
                )
                response.raise_for_status()
                data = response.json()
                message = ((data.get("choices") or [{}])[0].get("message") or {})
                text = message.get("content") or ""
                raw_usage = data.get("usage") or {}
                usage = TokenUsage(
                    prompt_tokens=int(raw_usage.get("prompt_tokens", 0) or 0),
                    completion_tokens=int(raw_usage.get("completion_tokens", 0) or 0),
                    total_tokens=int(raw_usage.get("total_tokens", 0) or 0),
                )
                if usage.total_tokens == 0:
                    usage = TokenUsage(prompt_tokens=max(1, sum(len(m.get("content", "")) for m in messages) // 2), completion_tokens=max(1, len(text) // 2))
                return LLMResponse(text=text, usage=usage, raw=data)
            except Exception as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Qwen API call failed after retries: {last_error}") from last_error

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Iterator[LLMStreamChunk]:
        """Stream chat completions from Qwen API."""
        if self.dry_run:
            # Dry-run mode: simulate streaming
            text = '{"label":"insufficient","answer":"A","confidence":0.0,"reason":"dry-run"}'
            for char in text:
                yield LLMStreamChunk(content=char)
            yield LLMStreamChunk(content="", finish_reason="stop")
            return

        url = self.settings.qwen_base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": resolve_chat_model(self.settings),
            "messages": messages,
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.answer_max_tokens,
            "stream": True,  # Enable streaming
        }

        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self._api_key()}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.settings.request_timeout_seconds,
                stream=True,  # Enable streaming response
            )
            response.raise_for_status()

            # Parse SSE stream
            for line in response.iter_lines():
                if not line:
                    continue

                line_str = line.decode("utf-8")
                if not line_str.startswith("data: "):
                    continue

                data_str = line_str[6:].strip()  # Remove "data: " prefix
                if data_str == "[DONE]":
                    break

                try:
                    import json
                    data = json.loads(data_str)
                    choices = data.get("choices", [])
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    finish_reason = choices[0].get("finish_reason")

                    if content or finish_reason:
                        yield LLMStreamChunk(content=content, finish_reason=finish_reason)

                except json.JSONDecodeError:
                    continue

        except Exception as exc:
            raise RuntimeError(f"Qwen streaming API call failed: {exc}") from exc
