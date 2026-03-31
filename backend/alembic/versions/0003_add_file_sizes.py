"""Add original_file_size and output_file_size columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("original_file_size", sa.BigInteger(), nullable=True))
    op.add_column("processing_jobs", sa.Column("output_file_size", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "output_file_size")
    op.drop_column("processing_jobs", "original_file_size")
