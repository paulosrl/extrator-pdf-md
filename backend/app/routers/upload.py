import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_async_db
from app.dependencies import get_current_user
from app.models.job import ProcessingJob, JobStatus
from app.models.user import User
from app.schemas.job import JobCreated
from app.services.storage import save_upload

router = APIRouter(tags=["upload"])

MAX_BYTES = settings.MAX_FILE_SIZE_MB * 1024 * 1024


@router.post("/upload", response_model=JobCreated, status_code=status.HTTP_202_ACCEPTED)
async def upload_pdf(
    file: UploadFile = File(...),
    use_llm: bool = Form(False),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    # Validate content type
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        # Also accept by filename extension
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="Apenas arquivos PDF são aceitos. Envie um arquivo com extensão .pdf.",
            )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Arquivo muito grande. Tamanho máximo: {settings.MAX_FILE_SIZE_MB} MB.",
        )

    if use_llm and not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=400,
            detail="Refinamento com IA não disponível: OPENAI_API_KEY não configurada.",
        )

    job_id = uuid.uuid4()
    storage_path = await save_upload(file_bytes, str(current_user.id), str(job_id))

    job = ProcessingJob(
        id=job_id,
        user_id=current_user.id,
        status=JobStatus.queued,
        original_filename=file.filename or "document.pdf",
        original_storage_path=storage_path,
        use_llm=use_llm,
    )
    db.add(job)
    await db.commit()

    # Enqueue Celery task (import here to avoid circular import at module load)
    from app.workers.tasks import process_pdf
    process_pdf.delay(str(job_id))

    return JobCreated(job_id=job_id)
