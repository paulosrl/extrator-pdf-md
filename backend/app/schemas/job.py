import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel

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
    llm_tokens_used: Optional[int]
    tokens_raw_output: Optional[int] = None
    raw_output_path: Optional[str] = None
    error_message: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class JobCreated(BaseModel):
    job_id: uuid.UUID
