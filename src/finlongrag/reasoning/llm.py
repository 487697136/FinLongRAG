"""LLM client boundary."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol

import requests

from finlongrag.core.config import Settings, get_api_key
from finlongrag.core.schema import TokenUsage


@dataclass
class LLMResponse:
    text: str
    usage: TokenUsage
    raw: dict | None = None


class ChatModel(Protocol):
    def chat(self, messages: list[dict[str, str]], *, max_tokens: int | None = None, temperature: float | None = None) -> LLMResponse:
        ...


class QwenChatModel:
    """DashScope OpenAI-compatible chat client with deterministic dry-run mode."""

    def __init__(self, settings: Settings, *, dry_run: bool = False) -> None:
        self.settings = settings
        self.dry_run = dry_run
        self.api_key = get_api_key()
        if not dry_run and not self.api_key:
            raise RuntimeError("Missing API key. Set DASHSCOPE_API_KEY or use dry_run=True.")

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
            "model": self.settings.qwen_model,
            "messages": messages,
            "temperature": self.settings.temperature if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.answer_max_tokens,
        }
        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
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

