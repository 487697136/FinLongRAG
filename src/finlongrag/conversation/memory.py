"""Conversation memory: rolling window + entity context + LLM rolling summary."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from finlongrag.storage.repository import ConversationRecord, MessageRecord

if TYPE_CHECKING:
    from finlongrag.reasoning.llm import ChatModel

HIGH_SIGNAL_RE = re.compile(
    r"\d|%|亿元|万元|元|第[一二三四五六七八九十百千万0-9]+[章节条款]|"
    r"营业收入|净利润|现金流|研发投入|保险责任|免责|处罚|期限|利率"
)

# LLM rolling summary is triggered when the conversation exceeds this many turns
ROLLING_SUMMARY_TURN_THRESHOLD = 10


class ConversationMemory:
    def __init__(
        self,
        *,
        recent_turns: int = 6,
        max_context_chars: int = 2400,
        llm: ChatModel | None = None,
    ) -> None:
        self.recent_turns = recent_turns
        self.max_context_chars = max_context_chars
        self._llm = llm

    def build_context(
        self,
        conversation: ConversationRecord | None,
        messages: list[MessageRecord],
        *,
        use_memory: bool = True,
        memory_turn_window: int | None = None,
    ) -> str:
        """Build conversation context string.

        When use_memory=False, returns an empty string so the pipeline treats
        the question as standalone (no history injection).
        """
        if not use_memory:
            return ""

        parts: list[str] = []
        if conversation and conversation.summary:
            parts.append(f"[会话摘要]\n{conversation.summary}")

        recent_turns = self.recent_turns if memory_turn_window is None else max(1, memory_turn_window)
        recent = messages[-recent_turns * 2 :]
        if recent:
            lines = ["[最近对话]"]
            for message in recent:
                role = "用户" if message.role == "user" else "助手"
                content = " ".join(message.content.split())
                lines.append(f"{role}: {content}")
            parts.append("\n".join(lines))

        facts = self.extract_high_signal_facts(messages)
        if facts:
            parts.append("[历史关键事实]\n" + "\n".join(f"- {fact}" for fact in facts[:12]))

        return "\n\n".join(parts)[: self.max_context_chars]

    def update_summary(self, previous_summary: str, messages: list[MessageRecord]) -> str:
        """Update conversation summary.

        Uses LLM rolling summarization when turn count exceeds threshold;
        otherwise falls back to heuristic sentence concatenation.
        """
        turn_count = sum(1 for m in messages if m.role == "user")
        if turn_count >= ROLLING_SUMMARY_TURN_THRESHOLD and self._llm is not None:
            return self._llm_rolling_summary(previous_summary, messages)
        return self._heuristic_summary(previous_summary, messages)

    def extract_entity_context(self, messages: list[MessageRecord]) -> dict[str, Any]:
        """Extract persistent entity context from conversation history.

        Returns a dict with keys: company, fiscal_year, doc_scope, kb_ids.
        These are merged into QueryRewriter.rewrite() as history_entities so
        that implicit references in follow-up questions are resolved.
        """
        all_text = " ".join(m.content for m in messages[-20:])

        # Company / institution names (simple heuristic — 2-8 CJK chars + 公司/集团/银行/保险)
        companies = re.findall(
            r"[\u4e00-\u9fff]{2,8}(?:公司|集团|银行|证券|保险|基金|股份|有限)", all_text
        )

        # Fiscal years
        fiscal_years = re.findall(r"(?:19|20)\d{2}年(?:[第]?[一二三四1-4]季度)?", all_text)

        # Doc types
        doc_scopes = re.findall(
            r"(?:年度?报告?|半年度?报告?|招股(?:说明)?书|季度?报告?|研究报告|基金(?:合同|招募说明书))",
            all_text,
        )

        return {
            "company": list(dict.fromkeys(companies))[:3],
            "fiscal_year": list(dict.fromkeys(fiscal_years))[:3],
            "doc_scope": list(dict.fromkeys(doc_scopes))[:2],
        }

    @staticmethod
    def extract_high_signal_facts(messages: list[MessageRecord]) -> list[str]:
        facts: list[str] = []
        seen: set[str] = set()
        for message in messages:
            if message.role not in {"assistant", "system"}:
                continue
            for sentence in _split_sentences(message.content):
                normalized = " ".join(sentence.split())
                if normalized and normalized not in seen and HIGH_SIGNAL_RE.search(normalized):
                    facts.append(normalized[:180])
                    seen.add(normalized)
        ranked = sorted(enumerate(facts), key=lambda item: (_score(item[1]), item[0]), reverse=True)
        keep = sorted(index for index, _ in ranked[:24])
        return [facts[index] for index in keep]

    # ── Private helpers ───────────────────────────────────────────────────────

    def _heuristic_summary(self, previous_summary: str, messages: list[MessageRecord]) -> str:
        facts = self.extract_high_signal_facts(messages)
        recent_user = [m.content.strip() for m in messages if m.role == "user"][-3:]
        lines: list[str] = []
        if previous_summary:
            lines.append(previous_summary.strip())
        if recent_user:
            lines.append("近期用户关注：" + "；".join(recent_user))
        if facts:
            lines.append("关键事实：" + "；".join(facts[:8]))
        return "\n".join(dict.fromkeys(line for line in lines if line))[:1200]

    def _llm_rolling_summary(self, previous_summary: str, messages: list[MessageRecord]) -> str:
        """LogicRAG-style rolling summary: Mem_new = LLM.summarize(Mem_old + last_2_turns)."""
        last_turns: list[str] = []
        for m in messages[-4:]:
            role = "用户" if m.role == "user" else "助手"
            last_turns.append(f"{role}: {m.content.strip()[:300]}")

        context = "\n".join(filter(None, [
            f"[历史摘要]\n{previous_summary}" if previous_summary else "",
            "[最近对话]\n" + "\n".join(last_turns) if last_turns else "",
        ]))

        messages_llm = [
            {
                "role": "system",
                "content": (
                    "你是金融对话摘要助手。将历史摘要与最新对话合并为一段简洁的摘要，"
                    "保留关键公司名、年份、指标和结论。摘要不超过400字。"
                ),
            },
            {"role": "user", "content": context[:3000]},
        ]
        try:
            response = self._llm.chat(messages_llm, temperature=0.0, max_tokens=512)
            return (response.text or "").strip()[:1200]
        except Exception:
            return self._heuristic_summary(previous_summary, messages)


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。！？；\n])", text or "") if len(part.strip()) >= 8]


def _score(text: str) -> int:
    return len(HIGH_SIGNAL_RE.findall(text))
