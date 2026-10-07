from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from knowledge_manager.materialized_views import invalidate_materialized_views
from pydantic import BaseModel, Field


class IngestionJob(BaseModel):
    job_id: str
    source_id: str
    trigger: str
    tenant_id: str = ""
    workspace_id: str = ""
    status: str = "queued"
    stage: str = "queued"
    payload_kind: str = ""
    payload_path: str = ""
    payload_meta: dict = Field(default_factory=dict)
    result_modules: list[dict] = Field(default_factory=list)
    worker_id: str = ""
    attempt_count: int = 0
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
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
    invalidate_materialized_views(kb_path, ["admin_dashboard"])
    return job


def create_ingestion_job(
    kb_path: Path,
    source_id: str,
    trigger: str,
    *,
    tenant_id: str = "",
    workspace_id: str = "",
) -> IngestionJob:
    if not tenant_id and not workspace_id:
        try:
            from knowledge_manager.source_ingestion import load_source_registry

            registry = load_source_registry(kb_path)
            source = registry.sources.get(source_id)
            if source is not None:
                tenant_id = source.tenant_id
                workspace_id = source.workspace_id
        except Exception:
            pass
    job = IngestionJob(
        job_id=f"job-{uuid4().hex[:12]}",
        source_id=source_id,
        trigger=trigger,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )
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


def claim_ingestion_job(
    kb_path: Path,
    job_id: str,
    worker_id: str,
    lease_seconds: int = 60,
) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "status": "running",
                "stage": "running",
                "worker_id": worker_id,
                "attempt_count": job.attempt_count + 1,
                "heartbeat_at": datetime.now(timezone.utc),
                "lease_expires_at": datetime.now(timezone.utc).replace(microsecond=0)
                + timedelta(seconds=lease_seconds),
            }
        ),
    )


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
                "stage": "completed",
                "pages_seen": pages_seen,
                "modules_staged": modules_staged,
                "modules_marked_stale": modules_marked_stale,
                "error": "",
                "lease_expires_at": None,
                "heartbeat_at": None,
            }
        ),
    )


def fail_ingestion_job(kb_path: Path, job_id: str, error: str) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "status": "failed",
                "stage": "failed",
                "error": error,
                "lease_expires_at": None,
                "heartbeat_at": None,
            }
        ),
    )


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
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "status": "queued",
                "stage": "queued",
                "worker_id": "",
                "lease_expires_at": None,
                "heartbeat_at": None,
            }
        ),
    )


def update_job_payload(
    kb_path: Path,
    job_id: str,
    *,
    payload_kind: str,
    payload_path: str = "",
    payload_meta: dict | None = None,
) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "payload_kind": payload_kind,
                "payload_path": payload_path,
                "payload_meta": payload_meta or {},
            }
        ),
    )


def update_job_stage(kb_path: Path, job_id: str, stage: str) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    updates = {"stage": stage}
    if job.status == "running":
        now = datetime.now(timezone.utc)
        updates["heartbeat_at"] = now
        updates["lease_expires_at"] = now.replace(microsecond=0) + timedelta(seconds=60)
    return _save_job(kb_path, job.model_copy(update=updates))


def renew_ingestion_job_lease(kb_path: Path, job_id: str, lease_seconds: int = 60) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    if job.status != "running":
        return job
    now = datetime.now(timezone.utc)
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "heartbeat_at": now,
                "lease_expires_at": now.replace(microsecond=0) + timedelta(seconds=lease_seconds),
            }
        ),
    )


def store_job_result_modules(kb_path: Path, job_id: str, modules: list[dict]) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    return _save_job(kb_path, job.model_copy(update={"result_modules": modules}))
