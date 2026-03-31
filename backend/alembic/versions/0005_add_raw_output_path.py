"""Add raw_output_path column for pre-LLM markdown

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("raw_output_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "raw_output_path")
