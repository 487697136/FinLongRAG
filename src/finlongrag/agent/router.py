"""Agent route selection.

Three execution paths:
- STRUCTURED: MCQ / multi-select / true-false with options → claim verification
- CONVERSATIONAL: greetings and meta questions → direct LLM, no retrieval
- RAG: everything else → rewrite → retrieve → rerank → answer

Routing uses a lightweight LLM classifier when available. Without an LLM (dry-run /
offline tests) the router defaults to RAG so document questions still work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from finlongrag.core.schema import Question

if TYPE_CHECKING:
    from finlongrag.reasoning.llm import ChatModel


class RouteType(str, Enum):
    CONVERSATIONAL = "conversational"
    STRUCTURED = "structured"
    RAG = "rag"


@dataclass(frozen=True)
class RouteDecision:
    route: RouteType
    reason: str
    confidence: float = 1.0
    llm_rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "route": self.route.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "llm_rationale": self.llm_rationale,
        }


_ROUTER_SYSTEM_PROMPT = (
    "你是问答系统路由分类器。判断用户消息是否需要查阅已上传文档才能准确回答。\n"
    "只输出一行，格式：<type>|<reason>\n"
    "type 只能是：\n"
    "- conversational：问候、感谢、询问助手身份/功能、闲聊，无需文档\n"
    "- rag：需要基于文档内容回答的问题（事实查询、分析、对比、总结、数值等）\n"
    "不确定时优先选 rag。"
)


class AgentRouter:
    """Minimal router: deterministic structured detection + LLM conversational gate."""

    def __init__(self, llm: ChatModel | None = None) -> None:
        self._llm = llm

    def decide(self, question: Question) -> RouteDecision:
        if question.options and question.answer_format in {"mcq", "multi", "tf"}:
            return RouteDecision(
                RouteType.STRUCTURED,
                "structured question with options",
                confidence=1.0,
            )

        text = question.question.strip()
        if not text:
            return RouteDecision(RouteType.RAG, "empty question defaults to RAG", confidence=0.5)

        if self._llm is not None:
            route, rationale = self._llm_classify(text)
            return RouteDecision(
                route,
                rationale or "llm routing",
                confidence=0.85,
                llm_rationale=rationale,
            )

        return RouteDecision(RouteType.RAG, "default document QA path", confidence=0.7)

    def _llm_classify(self, text: str) -> tuple[RouteType, str]:
        messages = [
            {"role": "system", "content": _ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": text[:500]},
        ]
        try:
            response = self._llm.chat(messages, temperature=0.0, max_tokens=64)
            raw = (response.text or "").strip()
            type_str, _, rationale = raw.partition("|")
            type_str = type_str.strip().lower()
            if type_str == "conversational":
                return RouteType.CONVERSATIONAL, rationale.strip() or raw
            return RouteType.RAG, rationale.strip() or raw
        except Exception:
            return RouteType.RAG, ""
