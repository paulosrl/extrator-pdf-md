"""Optimize indexes: drop redundant, add composite for list query

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-29

Changes:
- DROP ix_users_email (redundant — unique constraint users_email_key already provides a btree index on email)
- DROP ix_processing_jobs_user_id (replaced by composite)
- ADD ix_processing_jobs_user_created (user_id, created_at DESC)
    Covers the main list query: WHERE user_id = ? ORDER BY created_at DESC LIMIT 50
    Avoids filesort entirely — index scan returns rows already ordered.
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove índice redundante: unique constraint já cria o btree em email
    op.drop_index("ix_users_email", table_name="users")

    # Substitui índice simples por composto (user_id + created_at DESC)
    op.drop_index("ix_processing_jobs_user_id", table_name="processing_jobs")
    op.execute("""
        CREATE INDEX ix_processing_jobs_user_created
        ON processing_jobs (user_id, created_at DESC)
    """)


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_user_created", table_name="processing_jobs")
    op.create_index("ix_processing_jobs_user_id", "processing_jobs", ["user_id"])
    op.create_index("ix_users_email", "users", ["email"])
