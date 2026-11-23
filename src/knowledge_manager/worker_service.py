from __future__ import annotations

import time
from pathlib import Path

from knowledge_manager.ingestion_jobs import list_ingestion_jobs, requeue_expired_ingestion_job
from knowledge_manager.job_worker import run_pending_maintenance, run_single_job


def requeue_stale_jobs(kb_path: Path) -> list[str]:
    """扫描只是候选集合，回收在写锁内重读状态和租约后进行。"""
    requeued: list[str] = []
    for job in list_ingestion_jobs(kb_path):
        if job.status != "running":
            continue
        if requeue_expired_ingestion_job(kb_path, job.job_id, job.attempt_count):
            requeued.append(job.job_id)
    return requeued


def run_worker_loop(kb_path: Path, *, once: bool = False, poll_interval: float = 1.0) -> int:
    processed = 0
    while True:
        requeue_stale_jobs(kb_path)
        processed += run_pending_maintenance(kb_path, 20)
        queued = [job for job in list_ingestion_jobs(kb_path) if job.status == "queued"]
        for job in queued:
            run_single_job(kb_path, job.job_id)
            processed += 1
        if once:
            return processed
        time.sleep(poll_interval)
