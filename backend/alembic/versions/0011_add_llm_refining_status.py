"""Add llm_refining value to jobstatus enum

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-08
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE jobstatus ADD VALUE IF NOT EXISTS 'llm_refining'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op.
    pass
