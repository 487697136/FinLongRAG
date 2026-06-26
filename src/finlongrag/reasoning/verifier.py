"""Claim-level evidence verification."""

from __future__ import annotations

from finlongrag.core.schema import Claim, ClaimVerdict, TokenUsage
from finlongrag.reasoning.answer_parser import extract_json_object
from finlongrag.reasoning.llm import ChatModel
from finlongrag.reasoning.prompts import build_claim_verification_messages
from finlongrag.retrieval.evidence import select_evidence
from finlongrag.retrieval.queries import build_claim_queries
from finlongrag.retrieval.retriever import Retriever


class ClaimVerifier:
    def __init__(
        self,
        retriever: Retriever,
        llm: ChatModel,
        *,
        evidence_per_claim: int = 4,
        evidence_chars_per_claim: int = 3200,
    ) -> None:
        self.retriever = retriever
        self.llm = llm
        self.evidence_per_claim = evidence_per_claim
        self.evidence_chars_per_claim = evidence_chars_per_claim

    def verify(self, claim: Claim) -> tuple[ClaimVerdict, TokenUsage]:
        filter_doc_ids = set(claim.doc_scope) if claim.doc_scope else None
        candidates = self.retriever.retrieve_queries(
            build_claim_queries(claim),
            filter_doc_ids=filter_doc_ids,
            source=f"claim:{claim.option_key}",
        )
        evidence = select_evidence(
            claim,
            candidates,
            top_k=self.evidence_per_claim,
            max_chars=self.evidence_chars_per_claim,
        )
        response = self.llm.chat(build_claim_verification_messages(claim, evidence), max_tokens=512, temperature=0.0)
        obj = extract_json_object(response.text) or {}
        label = str(obj.get("label") or "insufficient").lower().strip()
        if label not in {"true", "false", "insufficient"}:
            label = "insufficient"
        try:
            confidence = max(0.0, min(1.0, float(obj.get("confidence", 0.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        citations = obj.get("citations") or []
        if isinstance(citations, str):
            citations = [citations]
        verdict = ClaimVerdict(
            claim_id=claim.claim_id,
            option_key=claim.option_key,
            label=label,  # type: ignore[arg-type]
            confidence=confidence,
            evidence=evidence,
            citations=[str(item) for item in citations],
            reason=str(obj.get("reason") or ""),
            metadata={"claim_type": claim.claim_type, "raw_response": response.text},
        )
        return verdict, response.usage

