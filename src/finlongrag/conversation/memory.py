"""Conversation memory window and compression."""

from __future__ import annotations

import re

from finlongrag.storage.repository import ConversationRecord, MessageRecord

HIGH_SIGNAL_RE = re.compile(
    r"\d|%|亿元|万元|元|第[一二三四五六七八九十百千万0-9]+[章节条款]|"
    r"营业收入|净利润|现金流|研发投入|保险责任|免责|处罚|期限|利率"
)


class ConversationMemory:
    def __init__(self, *, recent_turns: int = 6, max_context_chars: int = 2400) -> None:
        self.recent_turns = recent_turns
        self.max_context_chars = max_context_chars

    def build_context(self, conversation: ConversationRecord | None, messages: list[MessageRecord]) -> str:
        parts: list[str] = []
        if conversation and conversation.summary:
            parts.append(f"[会话摘要]\n{conversation.summary}")

        recent = messages[-self.recent_turns * 2 :]
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


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。！？；\n])", text or "") if len(part.strip()) >= 8]


def _score(text: str) -> int:
    return len(HIGH_SIGNAL_RE.findall(text))
