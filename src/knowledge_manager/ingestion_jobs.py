from __future__ import annotations

from knowledge_manager.file_locks import serialized_write

from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Any, Iterator
from uuid import uuid4

from knowledge_manager.materialized_views import invalidate_materialized_views
from knowledge_manager.json_io import atomic_write_text
from pydantic import BaseModel, Field

from knowledge_manager.schemas import StoredDatetime


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
    lease_expires_at: StoredDatetime | None = None
    heartbeat_at: StoredDatetime | None = None
    resume_cursor: str = ""
    pages_seen: int = 0
    modules_staged: int = 0
    modules_marked_stale: int = 0
    error: str = ""
    created_at: StoredDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: StoredDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JobClaimConflict(RuntimeError):
    """任务领取或执行尝试已失效，调用者必须停止提交。"""


def _aware(value: datetime) -> datetime:
    """兼容旧任务文件中的无时区时间，统一按UTC判断租约。"""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _require_attempt(kb_path: Path, job_id: str, attempt_count: int) -> IngestionJob:
    """在持有知识库写锁时核对当前执行和有效租约。"""
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    if (
        job.status != "running"
        or job.attempt_count != attempt_count
        or job.lease_expires_at is None
        or _aware(job.lease_expires_at) <= datetime.now(timezone.utc)
    ):
        raise JobClaimConflict(f"job {job_id} attempt {attempt_count} is no longer active")
    return job


@contextmanager
def ingestion_attempt(
    kb_path: Path, job_id: str, attempt_count: int, *, lease_lost: Event | None = None
) -> Iterator[IngestionJob]:
    """原子核对归属并提交本地结果；禁止在此上下文执行外部提取调用。"""
    from knowledge_manager.file_locks import kb_write_lock

    with kb_write_lock(kb_path):
        if lease_lost is not None and lease_lost.is_set():
            raise JobClaimConflict(f"job {job_id} heartbeat lost")
        yield _require_attempt(kb_path, job_id, attempt_count)


def _jobs_dir(kb_path: Path) -> Path:
    return kb_path / ".jobs" / "ingestion"


def _job_path(kb_path: Path, job_id: str) -> Path:
    return _jobs_dir(kb_path) / f"{job_id}.json"


def _save_job(kb_path: Path, job: IngestionJob) -> IngestionJob:
    from knowledge_manager.file_locks import kb_write_lock

    job = job.model_copy(update={"updated_at": datetime.now(timezone.utc)})
    with kb_write_lock(kb_path):
        path = _job_path(kb_path, job.job_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, job.model_dump_json(indent=2))
    invalidate_materialized_views(kb_path, ["admin_dashboard"])
    return job


@serialized_write
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


@serialized_write
def claim_ingestion_job(
    kb_path: Path,
    job_id: str,
    worker_id: str,
    lease_seconds: int = 60,
) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    if job.status in {"completed", "failed"}:
        raise JobClaimConflict(f"job {job_id} is terminal")
    now = datetime.now(timezone.utc)
    lease = job.lease_expires_at
    if job.status == "running" and lease is None:
        raise JobClaimConflict(f"job {job_id} requires explicit recovery")
    if job.status == "running" and lease is not None:
        if lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        if lease > now:
            raise JobClaimConflict(f"job {job_id} has an active lease")
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "status": "running",
                "stage": "running",
                "worker_id": worker_id,
                "attempt_count": job.attempt_count + 1,
                "heartbeat_at": now,
                "lease_expires_at": now + timedelta(seconds=lease_seconds),
            }
        ),
    )


@serialized_write
def complete_ingestion_job(
    kb_path: Path,
    job_id: str,
    *,
    attempt_count: int,
    pages_seen: int,
    modules_staged: int,
    modules_marked_stale: int = 0,
) -> IngestionJob:
    job = _require_attempt(kb_path, job_id, attempt_count)
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


@serialized_write
def fail_ingestion_job(
    kb_path: Path, job_id: str, error: str, *, attempt_count: int
) -> IngestionJob:
    """仅允许当前有效尝试记录失败，避免迟到异常覆盖接管者。"""
    job = _require_attempt(kb_path, job_id, attempt_count)
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


@serialized_write
def update_ingestion_checkpoint(
    kb_path: Path, job_id: str, cursor: str, pages_seen: int, *, attempt_count: int
) -> IngestionJob:
    job = _require_attempt(kb_path, job_id, attempt_count)
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "resume_cursor": cursor,
                "pages_seen": pages_seen,
            }
        ),
    )


@serialized_write
def resume_ingestion_job(kb_path: Path, job_id: str) -> IngestionJob:
    """显式人工重试失败或中断任务；已完成任务保持终态。"""
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)
    if job.status == "completed":
        raise JobClaimConflict(f"job {job_id} is terminal")
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


@serialized_write
def requeue_expired_ingestion_job(kb_path: Path, job_id: str, attempt_count: int) -> bool:
    """重读并原子回收扫描到的过期尝试，避免覆盖新心跳或接管者。"""
    job = load_ingestion_job(kb_path, job_id)
    if (
        job is None
        or job.status != "running"
        or job.attempt_count != attempt_count
        or (
            job.lease_expires_at is not None
            and _aware(job.lease_expires_at) > datetime.now(timezone.utc)
        )
    ):
        return False
    resume_ingestion_job(kb_path, job_id)
    return True


@serialized_write
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
    if job.status != "queued":
        raise JobClaimConflict(f"job {job_id} payload is already assigned")
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


@serialized_write
def update_job_stage(kb_path: Path, job_id: str, stage: str, *, attempt_count: int) -> IngestionJob:
    """当前尝试更新阶段时同时续租。"""
    job = _require_attempt(kb_path, job_id, attempt_count)
    now = datetime.now(timezone.utc)
    updates: dict[str, Any] = {
        "stage": stage,
        "heartbeat_at": now,
        "lease_expires_at": now + timedelta(seconds=60),
    }
    return _save_job(kb_path, job.model_copy(update=updates))


@serialized_write
def renew_ingestion_job_lease(
    kb_path: Path, job_id: str, lease_seconds: int = 60, *, attempt_count: int
) -> IngestionJob:
    """续租不能复活已经到期或失去归属的执行。"""
    job = _require_attempt(kb_path, job_id, attempt_count)
    now = datetime.now(timezone.utc)
    return _save_job(
        kb_path,
        job.model_copy(
            update={
                "heartbeat_at": now,
                "lease_expires_at": now + timedelta(seconds=lease_seconds),
            }
        ),
    )


@serialized_write
def store_job_result_modules(
    kb_path: Path, job_id: str, modules: list[dict], *, attempt_count: int
) -> IngestionJob:
    """结果引用仅属于当前有效尝试。"""
    job = _require_attempt(kb_path, job_id, attempt_count)
    return _save_job(kb_path, job.model_copy(update={"result_modules": modules}))
