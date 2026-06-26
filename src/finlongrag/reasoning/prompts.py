"""Prompt builders."""

from __future__ import annotations

from finlongrag.core.schema import Claim, Question, RetrievalResult
from finlongrag.retrieval.evidence import format_evidence


def build_claim_verification_messages(claim: Claim, evidence: list[RetrievalResult]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是金融长文本证据核验器。只能依据给定证据判断待核验陈述。"
                "重点核对主体、年份、数值、单位、条件和例外。证据不足时输出 insufficient。"
                "返回紧凑 JSON，不要 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"待核验陈述：\n{claim.claim_text}\n\n"
                f"证据：\n{format_evidence(evidence)}\n\n"
                '请返回 JSON：{"label":"true|false|insufficient","confidence":0.0,'
                '"citations":["E1"],"reason":"一句话说明"}'
            ),
        },
    ]


def build_open_answer_messages(
    question: Question,
    evidence: list[RetrievalResult],
    *,
    context_note: str = "",
) -> list[dict[str, str]]:
    context_block = f"\n\n辅助结构化信息：\n{context_note}" if context_note else ""
    return [
        {
            "role": "system",
            "content": "你是金融长文本问答助手。必须基于证据回答，并在答案中说明引用来源编号。",
        },
        {
            "role": "user",
            "content": f"问题：{question.question}\n\n证据：\n{format_evidence(evidence)}{context_block}\n\n请给出简洁、可核验的中文回答。",
        },
    ]
