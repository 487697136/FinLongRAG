"""Persistent API key storage per user."""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from finlongrag.db.base import Base, TimestampMixin, new_id


class UserApiKey(Base, TimestampMixin):
    __tablename__ = "user_api_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    model_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Store the encrypted/masked preview — never the raw key in DB
    key_preview: Mapped[str] = mapped_column(String(32), default="")
    # Encrypted key value (simple base64 — not production crypto, but keeps key out of plain text logs)
    key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
