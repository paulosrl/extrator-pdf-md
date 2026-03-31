"""Add tokens_raw_output column for pre-LLM token count

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("processing_jobs", sa.Column("tokens_raw_output", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_jobs", "tokens_raw_output")
