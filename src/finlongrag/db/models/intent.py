"""Intent taxonomy placeholder.

Reserved for future configurable routing. The current AgentRouter uses a
lightweight LLM classifier and does not read this table.
"""

from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from finlongrag.db.base import Base, JSONVariant, new_id


class IntentNode(Base):
    __tablename__ = "intent_nodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    parent_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("intent_nodes.id"), nullable=True)
    level: Mapped[str] = mapped_column(String(32), default="topic")
    name: Mapped[str] = mapped_column(String(120))
    kb_scope: Mapped[list] = mapped_column(JSONVariant, default=list)
    keywords: Mapped[list] = mapped_column(JSONVariant, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
