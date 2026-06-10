"""add github_pat to repositories

Revision ID: 003
Revises: 002
Create Date: 2026-06-10 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repositories", sa.Column("github_pat", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("repositories", "github_pat")
