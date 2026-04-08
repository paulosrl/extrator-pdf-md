import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, computed_field, model_validator

from app.models.job import JobStatus


class JobRead(BaseModel):
    id: uuid.UUID
    status: JobStatus
    original_filename: str
    pages_total: Optional[int]
    pages_ocr: Optional[int]
    pages_with_images: Optional[int]
    tokens_original: Optional[int]
    tokens_output: Optional[int]
    reduction_pct: Optional[float]
    original_file_size: Optional[int]
    output_file_size: Optional[int]
    use_llm: bool = False
    llm_model: Optional[str] = None
    llm_tokens_used: Optional[int]
    duration_local_s: Optional[float] = None
    duration_llm_s: Optional[float] = None
    tokens_raw_output: Optional[int] = None
    has_raw_md: bool = False
    has_rawtext: bool = False
    content_coverage_pct: Optional[float] = None
    blocks_total: Optional[int] = None
    blocks_kept: Optional[int] = None
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _derive_flags(cls, data: object) -> object:
        """Convert internal path fields to boolean presence flags."""
        if hasattr(data, "__dict__"):
            # SQLAlchemy model instance
            return {
                **{k: getattr(data, k) for k in data.__mapper__.column_attrs.keys()},
                "has_raw_md": bool(getattr(data, "raw_output_path", None)),
                "has_rawtext": bool(getattr(data, "rawtext_path", None)),
            }
        if isinstance(data, dict):
            data = dict(data)
            data["has_raw_md"] = bool(data.pop("raw_output_path", None))
            data["has_rawtext"] = bool(data.pop("rawtext_path", None))
        return data


class JobCreated(BaseModel):
    job_id: uuid.UUID
