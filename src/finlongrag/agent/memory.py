"""Per-question working memory and compression."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from finlongrag.core.schema import ClaimVerdict, RetrievalResult

_INFO_RE = re.compile(r"[0-9]|第[一二三四五六七八九十百千万0-9]+[章节条款]|%|万元|亿元|保险金|净利润|营业收入")


@dataclass
class WorkingMemory:
    qid: str
    question: str
    facts: list[str] = field(default_factory=list)
    verdicts: list[ClaimVerdict] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    max_facts: int = 32

    def add_evidence(self, evidence: list[RetrievalResult]) -> None:
        for item in evidence:
            if item.chunk_id not in self.evidence_ids:
                self.evidence_ids.append(item.chunk_id)
            for fact in self._facts_from_evidence(item):
                self.add_fact(fact)

    def add_verdict(self, verdict: ClaimVerdict) -> None:
        self.verdicts.append(verdict)
        self.add_evidence(verdict.evidence)
        if verdict.reason:
            self.add_fact(f"选项{verdict.option_key}: {verdict.label}，{verdict.reason}")

    def add_fact(self, fact: str) -> None:
        value = " ".join(str(fact or "").split())
        if value and value not in self.facts:
            self.facts.append(value)
            self._compress()

    def summary(self, max_chars: int = 1600) -> str:
        lines: list[str] = []
        if self.facts:
            lines.append("[关键事实]")
            lines.extend(f"- {fact}" for fact in self.facts)
        if self.verdicts:
            lines.append("[选项判定]")
            lines.extend(f"- {item.option_key}: {item.label} ({item.confidence:.2f})" for item in self.verdicts)
        return "\n".join(lines)[:max_chars]

    def to_dict(self) -> dict:
        return {
            "qid": self.qid,
            "facts": list(self.facts),
            "verdicts": [verdict.to_dict() for verdict in self.verdicts],
            "evidence_ids": list(self.evidence_ids),
        }

    def _compress(self) -> None:
        if len(self.facts) <= self.max_facts:
            return
        ranked = sorted(
            enumerate(self.facts),
            key=lambda item: (_info_score(item[1]), item[0]),
            reverse=True,
        )
        keep = sorted(index for index, _ in ranked[: self.max_facts])
        self.facts = [self.facts[index] for index in keep]

    @staticmethod
    def _facts_from_evidence(item: RetrievalResult) -> list[str]:
        facts: list[str] = []
        if item.metadata.get("section"):
            facts.append(f"{item.doc_id}#{item.metadata.get('page')}: {item.metadata.get('section')}")
        for number in item.metadata.get("numbers", [])[:5]:
            facts.append(f"{item.doc_id} 数值: {number}")
        for date in item.metadata.get("dates", [])[:3]:
            facts.append(f"{item.doc_id} 日期: {date}")
        return facts


def _info_score(text: str) -> int:
    return len(_INFO_RE.findall(text or ""))

