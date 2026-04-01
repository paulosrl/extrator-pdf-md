"""Add llm_model column to processing_jobs

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("llm_model", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "llm_model")
