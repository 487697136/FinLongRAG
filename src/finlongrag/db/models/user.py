"""User accounts.

Built in Phase 1 even though JWT login lands in Phase 7: retrofitting a
user_id foreign key onto conversations/knowledge_bases after rows already
exist is the expensive path, adding the column up front is free.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from finlongrag.db.base import Base, TimestampMixin, new_id


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(32), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
