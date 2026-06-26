"""Question and claim analysis."""

from __future__ import annotations

from finlongrag.core.schema import Claim, Question
from finlongrag.ingestion.chunker import extract_dates, extract_numbers
from finlongrag.retrieval.queries import extract_entities

COMPARISON_HINTS = ("比较", "对比", "高于", "低于", "超过", "不超过", "同比", "增长", "下降", "优于")
CLAUSE_HINTS = ("应当", "不得", "可以", "处罚", "罚款", "期限", "保险责任", "免责", "退保", "等待期")
METRIC_HINTS = ("营业收入", "净利润", "现金流", "研发投入", "分红", "票面利率", "发行规模", "市场规模")


class QuestionAnalyzer:
    def build_claims(self, question: Question) -> list[Claim]:
        if question.answer_format in {"mcq", "multi"}:
            return [
                self._build_option_claim(question, option_key, option_text)
                for option_key, option_text in sorted(question.options.items())
            ]
        if question.answer_format == "tf":
            return [self._build_option_claim(question, "stmt", question.question)]
        return []

    def _build_option_claim(self, question: Question, option_key: str, option_text: str) -> Claim:
        combined = f"{question.question} {option_text}"
        option_entities = extract_entities(option_text)
        question_entities = extract_entities(question.question)
        numbers = extract_numbers(combined)[:8]
        dates = extract_dates(combined)[:8]
        claim_type = self._infer_claim_type(combined, numbers)
        must_terms = _dedupe([*option_entities[:6], *numbers[:4], *dates[:4], *question_entities[:4]])[:12]
        should_terms = _dedupe([option_text, *option_entities[:6]])[:8]
        return Claim(
            claim_id=f"{question.qid}:{option_key}",
            question_id=question.qid,
            option_key=option_key,
            option_text=option_text,
            claim_text=f"{question.question}\n判断选项{option_key}是否正确：{option_text}".strip(),
            source_question=question.question,
            answer_format=question.answer_format,
            domain=question.domain,
            doc_scope=list(question.doc_ids),
            claim_type=claim_type,
            entities=_dedupe([*option_entities, *question_entities])[:12],
            numbers=numbers,
            dates=dates,
            must_terms=must_terms,
            should_terms=should_terms,
        )

    @staticmethod
    def _infer_claim_type(text: str, numbers: list[str]) -> str:
        if any(hint in text for hint in COMPARISON_HINTS):
            return "comparison"
        if any(hint in text for hint in CLAUSE_HINTS):
            return "clause_consequence"
        if any(hint in text for hint in METRIC_HINTS) or numbers:
            return "metric_fact"
        return "fact"


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = " ".join(str(item or "").split())
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output

