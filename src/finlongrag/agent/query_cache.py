"""In-process answer cache for repeated RAG queries."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from finlongrag.core.schema import AnswerResult, Question


@dataclass(frozen=True)
class CacheLookup:
    hit: bool
    key: str
    age_seconds: float = 0.0


class QueryAnswerCache:
  def __init__(self, *, max_entries: int = 256, ttl_seconds: int = 3600) -> None:
      self.max_entries = max(1, max_entries)
      self.ttl_seconds = max(60, ttl_seconds)
      self._entries: OrderedDict[str, tuple[float, AnswerResult]] = OrderedDict()

  def make_key(self, question: Question, *, mode: str = "auto", history: str = "") -> str:
      kb_id = ""
      if question.metadata:
          kb_ids = question.metadata.get("kb_ids") or []
          if kb_ids:
              kb_id = "|".join(sorted(str(k) for k in kb_ids))
          else:
              kb_id = str(question.metadata.get("kb_id") or "")
      normalized = " ".join(question.question.split()).lower()
      history_hash = hashlib.sha256((history or "").encode("utf-8")).hexdigest()[:16]
      raw = (
          f"{normalized}|{kb_id}|{mode}|{question.domain}|"
          f"{','.join(sorted(question.doc_ids))}|{history_hash}"
      )
      return hashlib.sha256(raw.encode("utf-8")).hexdigest()

  def lookup(
      self,
      question: Question,
      *,
      mode: str = "auto",
      history: str = "",
  ) -> tuple[CacheLookup, AnswerResult | None]:
      key = self.make_key(question, mode=mode, history=history)
      row = self._entries.get(key)
      if row is None:
          return CacheLookup(hit=False, key=key), None
      created_at, result = row
      age = time.time() - created_at
      if age > self.ttl_seconds:
          self._entries.pop(key, None)
          return CacheLookup(hit=False, key=key), None
      self._entries.move_to_end(key)
      cached = _clone_result(result, cache_age_seconds=round(age, 2))
      return CacheLookup(hit=True, key=key, age_seconds=age), cached

  def store(self, question: Question, result: AnswerResult, *, mode: str = "auto", history: str = "") -> str:
      key = self.make_key(question, mode=mode, history=history)
      self._entries[key] = (time.time(), _freeze_result(result))
      self._entries.move_to_end(key)
      while len(self._entries) > self.max_entries:
          self._entries.popitem(last=False)
      return key

  def clear(self) -> None:
      self._entries.clear()


def _freeze_result(result: AnswerResult) -> AnswerResult:
    return AnswerResult(
        qid=result.qid,
        answer=result.answer,
        domain=result.domain,
        answer_format=result.answer_format,
        confidence=result.confidence,
        evidence=list(result.evidence),
        verdicts=list(result.verdicts),
        token_usage=result.token_usage,
        raw_response=result.raw_response,
        metadata=dict(result.metadata or {}),
    )


def _clone_result(result: AnswerResult, *, cache_age_seconds: float) -> AnswerResult:
    metadata = dict(result.metadata or {})
    metadata["cache"] = {"hit": True, "age_seconds": cache_age_seconds}
    metadata["strategy"] = str(metadata.get("strategy") or "agentic_rag") + "_cached"
    return AnswerResult(
        qid=result.qid,
        answer=result.answer,
        domain=result.domain,
        answer_format=result.answer_format,
        confidence=result.confidence,
        evidence=list(result.evidence),
        verdicts=list(result.verdicts),
        token_usage=result.token_usage,
        raw_response=result.raw_response,
        metadata=metadata,
    )
