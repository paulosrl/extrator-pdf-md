import os
import uuid
from pathlib import Path

from app.config import settings


def get_upload_path(user_id: str, job_id: str) -> str:
    dir_path = Path(settings.STORAGE_PATH) / "uploads" / str(user_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    return str(dir_path / f"{job_id}.pdf")


def get_output_path(job_id: str) -> str:
    dir_path = Path(settings.STORAGE_PATH) / "outputs"
    dir_path.mkdir(parents=True, exist_ok=True)
    return str(dir_path / f"{job_id}.md")


async def save_upload(file_bytes: bytes, user_id: str, job_id: str) -> str:
    path = get_upload_path(user_id, job_id)
    with open(path, "wb") as f:
        f.write(file_bytes)
    return path


def save_md(job_id: str, content: str) -> str:
    path = get_output_path(job_id)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def save_raw_md(job_id: str, content: str) -> str:
    dir_path = Path(settings.STORAGE_PATH) / "outputs"
    dir_path.mkdir(parents=True, exist_ok=True)
    path = str(dir_path / f"{job_id}_raw.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def read_md(output_path: str) -> str:
    with open(output_path, "r", encoding="utf-8") as f:
        return f.read()
