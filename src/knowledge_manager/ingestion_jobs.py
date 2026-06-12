from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field


class IngestionJob(BaseModel):
    job_id: str
    source_id: str
    trigger: str
    status: str = "queued"
    worker_id: str = ""
    resume_cursor: str = ""
    pages_seen: int = 0
    modules_staged: int = 0
    modules_marked_stale: int = 0
    error: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def _jobs_dir(kb_path: Path) -> Path:
    return kb_path / ".jobs" / "ingestion"


def _job_path(kb_path: Path, job_id: str) -> Path:
    return _jobs_dir(kb_path) / f"{job_id}.json"


def _save_job(kb_path: Path, job: IngestionJob) -> IngestionJob:
    job = job.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    path = _job_path(kb_path, job.job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return job


def create_ingestion_job(kb_path: Path, source_id: str, trigger: str) -> IngestionJob:
    job = IngestionJob(job_id=f"job-{uuid4().hex[:12]}", source_id=source_id, trigger=trigger)
    return _save_job(kb_path, job)


def load_ingestion_job(kb_path: Path, job_id: str) -> IngestionJob | None:
    path = _job_path(kb_path, job_id)
    if not path.exists():
        return None
    return IngestionJob.model_validate_json(path.read_text(encoding="utf-8"))


def list_ingestion_jobs(kb_path: Path) -> list[IngestionJob]:
    jobs_dir = _jobs_dir(kb_path)
    if not jobs_dir.exists():
        return []
    jobs = [
        IngestionJob.model_validate_json(path.read_text(encoding="utf-8"))
        for path in jobs_dir.glob("*.json")
    ]
    jobs.sort(key=lambda item: item.created_at, reverse=True)
    return jobs


def claim_ingestion_job(kb_path: Path, job_id: str, worker_id: str) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(kb_path, job.model_copy(update={"status": "running", "worker_id": worker_id}))


def complete_ingestion_job(
    kb_path: Path,
    job_id: str,
    *,
    pages_seen: int,
    modules_staged: int,
    modules_marked_stale: int = 0,
) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "status": "completed",
                "pages_seen": pages_seen,
                "modules_staged": modules_staged,
                "modules_marked_stale": modules_marked_stale,
                "error": "",
            }
        ),
    )


def fail_ingestion_job(kb_path: Path, job_id: str, error: str) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(kb_path, job.model_copy(update={"status": "failed", "error": error}))


def update_ingestion_checkpoint(kb_path: Path, job_id: str, cursor: str, pages_seen: int) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "resume_cursor": cursor,
                "pages_seen": pages_seen,
            }
        ),
    )


def resume_ingestion_job(kb_path: Path, job_id: str) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(kb_path, job.model_copy(update={"status": "queued"}))
