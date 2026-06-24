"""add warning to ingestion_runs

Revision ID: 004
Revises: 003
Create Date: 2026-06-23 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("warning", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_runs", "warning")
