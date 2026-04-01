"""Add duration_local_s and duration_llm_s to processing_jobs

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("duration_local_s", sa.Float(), nullable=True))
    op.add_column("processing_jobs", sa.Column("duration_llm_s", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "duration_llm_s")
    op.drop_column("processing_jobs", "duration_local_s")
