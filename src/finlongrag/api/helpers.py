"""Shared API helpers without FastAPI imports."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol


class UploadReader(Protocol):
    filename: str | None

    async def read(self, size: int = -1) -> bytes: ...


class UploadTooLargeError(Exception):
    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        super().__init__(f"upload exceeds {max_bytes} bytes")


def resolve_query_kb_scope(
    *,
    knowledge_base_id: str | int | None,
    kb_ids: list[str] | None,
    user_id: str,
    get_knowledge_base: Callable[[str, str], Any],
) -> tuple[str | None, list[str] | None]:
    """Resolve KB scope for a query and verify each KB belongs to the user."""
    kb_id: str | None = None
    resolved_kb_ids: list[str] | None = None
    if kb_ids:
        resolved_kb_ids = [str(kid) for kid in kb_ids if kid]
        for kid in resolved_kb_ids:
            get_knowledge_base(kid, user_id)
        kb_id = resolved_kb_ids[0] if resolved_kb_ids else ""
    elif knowledge_base_id not in (None, ""):
        kb_id = str(knowledge_base_id)
        get_knowledge_base(kb_id, user_id)
    if kb_id and resolved_kb_ids and len(resolved_kb_ids) == 1:
        resolved_kb_ids = [kb_id]
    return kb_id, resolved_kb_ids


def get_user_kb(service, kb_id: str, user_id: str):
    """Return a knowledge base or raise KeyError (mapped to HTTP 404 by the app)."""
    return service.get_knowledge_base(kb_id, user_id=user_id)


def redact_database_url(database_url: str) -> str:
    """Return a non-sensitive placeholder for health/status responses."""
    if not database_url:
        return "<not configured>"
    return "<configured>"


async def read_upload_limited(file: UploadReader, max_bytes: int) -> bytes:
    """Read an upload with a hard size cap."""
    chunks: list[bytes] = []
    total = 0
    while True:
        piece = await file.read(1024 * 1024)
        if not piece:
            break
        total += len(piece)
        if total > max_bytes:
            raise UploadTooLargeError(max_bytes)
        chunks.append(piece)
    return b"".join(chunks)


def validate_upload_filename(filename: str, allowed_extensions: tuple[str, ...] | list[str]) -> str:
    from pathlib import Path

    suffix = Path(filename).suffix.lower()
    allowed = {ext.lower() for ext in allowed_extensions}
    if suffix not in allowed:
        raise ValueError(f"unsupported file type '{suffix}'")
    return suffix
