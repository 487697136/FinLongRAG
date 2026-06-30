"""Prompt builders."""

from __future__ import annotations

from finlongrag.core.schema import Claim, Question, RetrievalResult
from finlongrag.retrieval.evidence import format_evidence


def build_claim_verification_messages(claim: Claim, evidence: list[RetrievalResult]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是长文本证据核验器。只能依据给定证据判断待核验陈述。"
                "重点核对主体、时间、数值、单位、条件和例外。证据不足时输出 insufficient。"
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
    tool_context: str = "",
) -> list[dict[str, str]]:
    context_block = f"\n\n辅助结构化信息：\n{context_note}" if context_note else ""
    tool_block = f"\n\n{tool_context}" if tool_context else ""
    return [
        {
            "role": "system",
            "content": (
                "你是长文本智能问答助手。必须严格基于给定证据回答，"
                "每个关键结论标注引用来源编号 [En]。"
                "若提供数值事实账本或计算结果，优先使用其中的确定性数值，不要自行心算。"
                "证据不足时明确说明，不要编造。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"问题：{question.question}\n\n"
                f"证据：\n{format_evidence(evidence)}{context_block}{tool_block}\n\n"
                "请给出结构清晰、可核验的中文回答。"
            ),
        },
    ]
