"""Add content coverage and block count metrics to processing_jobs

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_jobs",
        sa.Column("rawtext_path", sa.Text(), nullable=True))
    op.add_column("processing_jobs",
        sa.Column("content_coverage_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("processing_jobs",
        sa.Column("blocks_total", sa.Integer(), nullable=True))
    op.add_column("processing_jobs",
        sa.Column("blocks_kept", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "blocks_kept")
    op.drop_column("processing_jobs", "blocks_total")
    op.drop_column("processing_jobs", "content_coverage_pct")
    op.drop_column("processing_jobs", "rawtext_path")
