"""Deterministic query construction."""

from __future__ import annotations

import re

from finlongrag.core.schema import Claim, Question
from finlongrag.ingestion.chunker import extract_dates, extract_numbers

RELATION_TERMS = (
    "营业收入",
    "净利润",
    "经营活动现金流量净额",
    "研发投入",
    "分红",
    "保险责任",
    "保险金",
    "等待期",
    "退保",
    "罚款",
    "处罚",
    "期限",
    "票面利率",
    "发行规模",
    "募集资金",
    "信用评级",
    "市场规模",
    "渗透率",
)


def question_with_options(question: Question) -> str:
    return "\n".join([question.question, question.options_text()]).strip()


def build_question_queries(question: Question) -> list[str]:
    payload = question_with_options(question)
    queries = [payload, question.question]
    relation_terms = [term for term in RELATION_TERMS if term in payload]
    if relation_terms:
        queries.append(" ".join(relation_terms + extract_dates(payload)[:4] + extract_numbers(payload)[:4]))
    for key, value in sorted(question.options.items()):
        queries.append(f"{question.question} {key} {value}")
    return _dedupe(queries)[:8]


def build_claim_queries(claim: Claim) -> list[str]:
    predicates = [term for term in RELATION_TERMS if term in f"{claim.source_question} {claim.option_text}"]
    queries = [
        claim.claim_text,
        " ".join([*claim.must_terms, *claim.should_terms]),
        " ".join(predicates + claim.dates[:4]),
    ]
    if claim.claim_type in {"metric_fact", "comparison"}:
        queries.append(" ".join([*predicates, "单位", "本期", "上期", "同比", *claim.dates[:2]]))
    if claim.claim_type == "clause_consequence":
        queries.append(" ".join([*predicates, "应当", "不得", "除外", "期限"]))
    return _dedupe(queries)[:6]


def extract_entities(text: str) -> list[str]:
    terms = re.findall(r"[\u4e00-\u9fffA-Za-z0-9][\u4e00-\u9fffA-Za-z0-9_.（）()%-]{1,32}", text or "")
    noise = {"下列", "以下", "关于", "根据", "正确", "错误", "说法", "描述"}
    return _dedupe([term for term in terms if term not in noise and len(term) >= 2])[:12]


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in items:
        value = " ".join(str(item or "").split())
        if value and value not in seen:
            output.append(value)
            seen.add(value)
    return output

