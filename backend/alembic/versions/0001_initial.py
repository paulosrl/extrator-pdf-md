"""Initial schema: users and processing_jobs

Revision ID: 0001
Revises:
Create Date: 2026-03-28
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE jobstatus AS ENUM ('queued', 'ocr', 'extracting', 'done', 'error');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("queued", "ocr", "extracting", "done", "error", name="jobstatus", create_type=False),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("original_storage_path", sa.Text, nullable=False),
        sa.Column("output_storage_path", sa.Text, nullable=True),
        sa.Column("pages_total", sa.Integer, nullable=True),
        sa.Column("pages_ocr", sa.Integer, nullable=True),
        sa.Column("pages_with_images", sa.Integer, nullable=True),
        sa.Column("tokens_original", sa.Integer, nullable=True),
        sa.Column("tokens_output", sa.Integer, nullable=True),
        sa.Column("reduction_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_processing_jobs_user_id", "processing_jobs", ["user_id"])


def downgrade() -> None:
    op.drop_table("processing_jobs")
    op.drop_index("ix_users_email", "users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS jobstatus")
