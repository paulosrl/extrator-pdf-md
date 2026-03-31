import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_async_db
from app.dependencies import get_current_user
from app.models.job import ProcessingJob, JobStatus
from app.models.user import User
from app.schemas.job import JobRead

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=List[JobRead])
async def list_jobs(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ProcessingJob)
        .where(ProcessingJob.user_id == current_user.id)
        .order_by(ProcessingJob.created_at.desc())
        .limit(50)
    )
    return result.scalars().all()


@router.get("/{job_id}", response_model=JobRead)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


@router.get("/{job_id}/download")
async def download_md(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if job.status != JobStatus.done or not job.output_storage_path:
        raise HTTPException(status_code=404, detail="Arquivo ainda não disponível")

    filename = job.original_filename.rsplit(".", 1)[0] + ".md"
    return FileResponse(
        path=job.output_storage_path,
        media_type="text/markdown",
        filename=filename,
    )


@router.get("/{job_id}/download/raw")
async def download_raw_md(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_id,
            ProcessingJob.user_id == current_user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if job.status != JobStatus.done or not job.raw_output_path:
        raise HTTPException(status_code=404, detail="Arquivo raw não disponível")

    filename = job.original_filename.rsplit(".", 1)[0] + "_local.md"
    return FileResponse(
        path=job.raw_output_path,
        media_type="text/markdown",
        filename=filename,
    )
