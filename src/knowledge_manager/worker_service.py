from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from knowledge_manager.ingestion_jobs import list_ingestion_jobs, resume_ingestion_job
from knowledge_manager.job_worker import run_pending_maintenance, run_single_job


def requeue_stale_jobs(kb_path: Path) -> list[str]:
    requeued: list[str] = []
    now = datetime.now(timezone.utc)
    for job in list_ingestion_jobs(kb_path):
        if job.status != "running" or job.lease_expires_at is None:
            continue
        lease = job.lease_expires_at
        if lease.tzinfo is None:
            lease = lease.replace(tzinfo=timezone.utc)
        if lease < now:
            resume_ingestion_job(kb_path, job.job_id)
            requeued.append(job.job_id)
    return requeued


def run_worker_loop(kb_path: Path, *, once: bool = False, poll_interval: float = 1.0) -> int:
    processed = 0
    requeue_stale_jobs(kb_path)
    while True:
        processed += run_pending_maintenance(kb_path, 20)
        queued = [job for job in list_ingestion_jobs(kb_path) if job.status == "queued"]
        for job in queued:
            run_single_job(kb_path, job.job_id)
            processed += 1
        if once:
            return processed
        time.sleep(poll_interval)
