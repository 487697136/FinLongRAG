"""evaluation metadata tables

Revision ID: 6a1e3d7b2c90
Revises: 9f7c1d2a4b63
Create Date: 2026-06-26 19:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

revision: str = "6a1e3d7b2c90"
down_revision: str | None = "cdc93c903ef4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    json_variant = sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), "postgresql")

    test_sets = sa.Table(
        "evaluation_test_sets",
        metadata,
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sheet_names", json_variant, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("file_name", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("file_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    test_sets.create(bind, checkfirst=True)
    sa.Index("ix_evaluation_test_sets_created_at", test_sets.c.created_at).create(bind, checkfirst=True)

    eval_runs = sa.Table(
        "evaluation_runs",
        metadata,
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("kb_id", sa.String(length=64), nullable=False),
        sa.Column("kb_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("test_set_id", sa.String(length=32), nullable=False),
        sa.Column("test_set_name", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metrics", json_variant, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("details", json_variant, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("progress_current", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("finished_at", sa.String(length=64), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("id"),
    )
    eval_runs.create(bind, checkfirst=True)
    sa.Index("ix_evaluation_runs_created_at", eval_runs.c.created_at).create(bind, checkfirst=True)
    sa.Index("ix_evaluation_runs_kb_id", eval_runs.c.kb_id).create(bind, checkfirst=True)
    sa.Index("ix_evaluation_runs_test_set_id", eval_runs.c.test_set_id).create(bind, checkfirst=True)


def downgrade() -> None:
    op.drop_index("ix_evaluation_runs_test_set_id", table_name="evaluation_runs", if_exists=True)
    op.drop_index("ix_evaluation_runs_kb_id", table_name="evaluation_runs", if_exists=True)
    op.drop_index("ix_evaluation_runs_created_at", table_name="evaluation_runs", if_exists=True)
    op.drop_table("evaluation_runs", if_exists=True)
    op.drop_index("ix_evaluation_test_sets_created_at", table_name="evaluation_test_sets", if_exists=True)
    op.drop_table("evaluation_test_sets", if_exists=True)
