import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import String, DateTime, Integer, Text, Numeric, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobStatus(str, enum.Enum):
    queued = "queued"
    ocr = "ocr"
    extracting = "extracting"
    done = "done"
    error = "error"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="jobstatus"), nullable=False, default=JobStatus.queued
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    output_storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_output_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pages_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pages_ocr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pages_with_images: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_original: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reduction_pct: Mapped[Optional[float]] = mapped_column(Numeric(7, 2), nullable=True)
    original_file_size: Mapped[Optional[int]] = mapped_column(sa.BigInteger(), nullable=True)
    output_file_size: Mapped[Optional[int]] = mapped_column(sa.BigInteger(), nullable=True)
    use_llm: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False, default=False)
    llm_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    llm_tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_local_s: Mapped[Optional[float]] = mapped_column(sa.Float(), nullable=True)
    duration_llm_s: Mapped[Optional[float]] = mapped_column(sa.Float(), nullable=True)
    tokens_raw_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
