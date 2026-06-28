"""increase ingestion_tasks stage column length

Revision ID: 6b1a91b312b3
Revises: 6a1e3d7b2c90
Create Date: 2026-06-27 20:00:42.350003

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b1a91b312b3'
down_revision: Union[str, None] = '6a1e3d7b2c90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Increase stage column length from 32 to 128
    op.alter_column('ingestion_tasks', 'stage',
                    existing_type=sa.String(32),
                    type_=sa.String(128),
                    existing_nullable=False)


def downgrade() -> None:
    # Revert stage column length from 128 to 32
    op.alter_column('ingestion_tasks', 'stage',
                    existing_type=sa.String(128),
                    type_=sa.String(32),
                    existing_nullable=False)
