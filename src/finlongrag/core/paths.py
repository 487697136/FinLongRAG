"""Path and dataset discovery utilities."""

from __future__ import annotations

from pathlib import Path

from finlongrag.core.config import Settings
from finlongrag.core.io import read_json
from finlongrag.core.schema import Document, Question

SUPPORTED_SUFFIXES = {".pdf", ".txt", ".md", ".html", ".htm"}


class DataRegistry:
    """Resolve documents and questions from a dataset-like directory layout."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings.from_file()
        self._file_index: dict[str, dict[str, Path]] = {}

    def question_files(self) -> list[Path]:
        root = self.settings.questions_root
        if root.is_file():
            return [root]
        if not root.exists():
            return []
        return sorted(root.glob("*.json"))

    def load_questions(self, domains: set[str] | None = None) -> list[Question]:
        output: list[Question] = []
        for path in self.question_files():
            payload = read_json(path)
            rows = payload if isinstance(payload, list) else payload.get("questions", [])
            for row in rows:
                question = Question.from_dict(row)
                if domains and question.domain not in domains:
                    continue
                output.append(question)
        return output

    def resolve_source_file(self, domain: str, doc_id: str) -> Path | None:
        index = self._domain_index(domain)
        key = str(doc_id).strip().lower()
        if key in index:
            return index[key]
        stripped = key.lstrip("0")
        if stripped and stripped in index:
            return index[stripped]
        return None

    def build_documents_for_questions(self, questions: list[Question]) -> list[Document]:
        seen: set[tuple[str, str]] = set()
        output: list[Document] = []
        for question in questions:
            for doc_id in question.doc_ids:
                key = (question.domain, doc_id)
                if key in seen:
                    continue
                seen.add(key)
                path = self.resolve_source_file(question.domain, doc_id)
                if path is None:
                    continue
                output.append(
                    Document(
                        doc_id=doc_id,
                        domain=question.domain,
                        title=path.stem,
                        path=str(path),
                        metadata={"source_suffix": path.suffix.lower()},
                    )
                )
        return output

    def _domain_index(self, domain: str) -> dict[str, Path]:
        if domain in self._file_index:
            return self._file_index[domain]
        root = self.settings.raw_root / domain
        index: dict[str, Path] = {}
        if root.exists():
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                    continue
                key = path.stem.lower()
                if key not in index or "attachments" not in str(path.parent).lower():
                    index[key] = path
        self._file_index[domain] = index
        return index
