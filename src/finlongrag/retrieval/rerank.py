"""DashScope evidence reranking."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import httpx

from finlongrag.core.config import Settings, get_api_key
from finlongrag.core.schema import Question, RetrievalResult


@dataclass(frozen=True)
class RerankReport:
    candidate_count: int
    selected_count: int
    covered_doc_ids: list[str]
    scoring: list[dict]

    def to_dict(self) -> dict:
        return asdict(self)


class DashScopeRerankError(RuntimeError):
    """Raised when DashScope rerank fails."""


@dataclass(frozen=True)
class DashScopeEvidenceReranker:
    api_key: str
    model: str = "qwen3-rerank"
    base_url: str = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    timeout_seconds: int = 120

    def rerank(
        self,
        question: Question,
        candidates: list[RetrievalResult],
        *,
        top_k: int = 24,
    ) -> tuple[list[RetrievalResult], RerankReport]:
        unique = _dedupe(candidates)
        if not unique:
            return [], RerankReport(0, 0, [], [])

        query = f"{question.question} {' '.join(question.options.values())}".strip()
        scored = self._rerank_once(query, [item.evidence_text for item in unique])
        ranked: list[tuple[float, RetrievalResult]] = []
        for index, score in scored:
            if index < 0 or index >= len(unique):
                continue
            item = unique[index]
            item.metadata["rerank_score"] = round(float(score), 6)
            item.metadata["rerank_provider"] = "dashscope"
            item.metadata["rerank_model"] = self.model
            ranked.append((float(score), item))

        ordered = [item for _, item in sorted(ranked, key=lambda row: (row[0], row[1].score), reverse=True)]
        selected = _balanced_select(question, ordered, top_k=top_k)
        selected_ids = {item.chunk_id for item in selected}
        scoring = [
            {
                "chunk_id": item.chunk_id,
                "doc_id": item.doc_id,
                "score": item.metadata.get("rerank_score"),
                "provider": "dashscope",
                "model": self.model,
            }
            for item in ordered
            if item.chunk_id in selected_ids
        ]
        return selected, RerankReport(
            candidate_count=len(candidates),
            selected_count=len(selected),
            covered_doc_ids=list(dict.fromkeys(item.doc_id for item in selected)),
            scoring=scoring,
        )

    def _rerank_once(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": {"query": query, "documents": documents},
            "parameters": {"return_documents": False, "top_n": len(documents)},
        }
        try:
            response = httpx.post(self.base_url, headers=headers, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DashScopeRerankError(f"DashScope rerank request failed: {exc}") from exc
        data = response.json()
        results = (data.get("output") or {}).get("results") or data.get("results")
        if not isinstance(results, list):
            raise DashScopeRerankError(f"unexpected rerank response shape: {data}")

        output: list[tuple[int, float]] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            index = row.get("index")
            score = row.get("relevance_score", row.get("score"))
            if index is None or score is None:
                continue
            output.append((int(index), float(score)))
        return output


def create_evidence_reranker(settings: Settings) -> DashScopeEvidenceReranker:
    provider = settings.rerank_provider.strip().lower()
    if provider != "dashscope":
        raise DashScopeRerankError("FINLONGRAG_RERANK_PROVIDER must be dashscope")
    api_key = get_api_key()
    if not api_key:
        raise DashScopeRerankError("DASHSCOPE_API_KEY is required for qwen3-rerank")
    return DashScopeEvidenceReranker(
        api_key=api_key,
        model=settings.rerank_model,
        base_url=settings.rerank_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )


def _dedupe(candidates: list[RetrievalResult]) -> list[RetrievalResult]:
    output: dict[str, RetrievalResult] = {}
    for item in candidates:
        current = output.get(item.chunk_id)
        if current is None or item.score > current.score:
            output[item.chunk_id] = item
    return list(output.values())


def _balanced_select(question: Question, ordered: list[RetrievalResult], *, top_k: int) -> list[RetrievalResult]:
    selected: list[RetrievalResult] = []
    seen: set[str] = set()

    def add(item: RetrievalResult) -> None:
        if item.chunk_id not in seen and len(selected) < top_k:
            selected.append(item)
            seen.add(item.chunk_id)

    for doc_id in question.doc_ids:
        item = next((row for row in ordered if row.doc_id == doc_id), None)
        if item is not None:
            add(item)
    for item in ordered:
        add(item)
        if len(selected) >= top_k:
            break
    return selected
