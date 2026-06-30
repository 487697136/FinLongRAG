"""Request-scoped DashScope API key resolution."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from sqlalchemy import select

from finlongrag.core.secrets import decrypt_secret
from finlongrag.db import get_sync_sessionmaker
from finlongrag.db.models.api_key import UserApiKey

_request_api_key: ContextVar[str | None] = ContextVar("request_dashscope_api_key", default=None)


def get_request_api_key() -> str | None:
    return _request_api_key.get()


def load_user_api_key(database_url: str, user_id: str, provider: str | None = None) -> str | None:
    """Load the user's saved DashScope-family API key from the database."""
    wanted = (provider or "dashscope").strip().lower()
    if not wanted.startswith("dashscope"):
        return None
    try:
        Session = get_sync_sessionmaker(database_url)
        with Session() as session:
            rows = session.execute(
                select(UserApiKey)
                .where(UserApiKey.user_id == user_id)
                .order_by(UserApiKey.created_at.desc())
            ).scalars().all()
            for row in rows:
                if not str(row.provider).lower().startswith("dashscope"):
                    continue
                if provider and row.provider.lower() != wanted:
                    continue
                return decrypt_secret(row.key_encrypted)
    except Exception:
        return None
    return None


@contextmanager
def user_api_key_scope(
    database_url: str,
    user_id: str,
    *,
    provider: str | None = None,
) -> Iterator[None]:
    key = load_user_api_key(database_url, user_id, provider)
    if not key:
        yield
        return
    token = _request_api_key.set(key)
    try:
        yield
    finally:
        _request_api_key.reset(token)
