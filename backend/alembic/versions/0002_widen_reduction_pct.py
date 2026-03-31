"""Widen reduction_pct column from NUMERIC(5,2) to NUMERIC(7,2)

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "processing_jobs",
        "reduction_pct",
        type_=sa.Numeric(7, 2),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "processing_jobs",
        "reduction_pct",
        type_=sa.Numeric(5, 2),
        existing_nullable=True,
    )
