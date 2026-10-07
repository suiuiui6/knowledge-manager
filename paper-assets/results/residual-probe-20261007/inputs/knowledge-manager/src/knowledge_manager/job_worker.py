from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from threading import Event, Lock, Thread
from pathlib import Path
from typing import Any
from uuid import uuid4

from knowledge_manager.ingestion_jobs import (
    IngestionJob,
    claim_ingestion_job,
    complete_ingestion_job,
    fail_ingestion_job,
    load_ingestion_job,
    renew_ingestion_job_lease,
    store_job_result_modules,
    update_job_stage,
)


_MAINTENANCE_WORKERS: set[str] = set()
_MAINTENANCE_WORKERS_LOCK = Lock()
JOB_HEARTBEAT_INTERVAL_SECONDS = 15.0
JOB_LEASE_SECONDS = 60


def _maintenance_dir(kb_path: Path) -> Path:
    return kb_path / ".cache" / "maintenance"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _maintenance_subject(action: str, payload: dict[str, Any]) -> str | None:
    if action == "module_saved":
        module = payload.get("module", {})
        module_id = module.get("id")
        category = module.get("category")
        if module_id and category:
            return f"{category}/{module_id}"
        return None
    if action == "module_deleted":
        module_id = payload.get("module_id")
        category = payload.get("category")
        if module_id and category:
            return f"{category}/{module_id}"
    return None


def _prune_superseded_maintenance_jobs(kb_path: Path, action: str, payload: dict[str, Any]) -> None:
    subject = _maintenance_subject(action, payload)
    if not subject:
        return
    queue_dir = _maintenance_dir(kb_path)
    if not queue_dir.exists():
        return
    for queued_path in queue_dir.glob("*.queued.json"):
        try:
            queued_payload = json.loads(queued_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        queued_subject = _maintenance_subject(
            str(queued_payload.get("action") or ""),
            queued_payload.get("payload", {}),
        )
        if queued_subject == subject:
            queued_path.unlink(missing_ok=True)


def _maintenance_worker_main(kb_path: Path) -> None:
    try:
        time.sleep(0.5)
        while run_pending_maintenance(kb_path, 20):
            pass
    finally:
        with _MAINTENANCE_WORKERS_LOCK:
            _MAINTENANCE_WORKERS.discard(str(kb_path.resolve()))


def _ensure_maintenance_worker(kb_path: Path) -> None:
    worker_key = str(kb_path.resolve())
    with _MAINTENANCE_WORKERS_LOCK:
        if worker_key in _MAINTENANCE_WORKERS:
            return
        _MAINTENANCE_WORKERS.add(worker_key)
    Thread(target=_maintenance_worker_main, args=(kb_path,), daemon=True).start()


def enqueue_local_maintenance(kb_path: Path, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    job_id = f"maint-{uuid4().hex[:12]}"
    queued_at = datetime.now(timezone.utc).isoformat()
    _prune_superseded_maintenance_jobs(kb_path, action, payload)
    job_payload = {
        "job_id": job_id,
        "action": action,
        "payload": payload,
        "status": "queued",
        "queued_at": queued_at,
    }
    queued_path = _maintenance_dir(kb_path) / f"{job_id}.queued.json"
    _write_json(queued_path, job_payload)
    return {"deferred": True, "job_id": job_id, "action": action, "queued_at": queued_at}


def run_pending_maintenance(kb_path: Path, limit: int = 20) -> int:
    from knowledge_manager.storage import run_deferred_maintenance_action

    processed = 0
    queue_dir = _maintenance_dir(kb_path)
    if not queue_dir.exists():
        return 0

    for queued_path in sorted(queue_dir.glob("*.queued.json")):
        if processed >= limit:
            break
        running_path = queued_path.with_name(queued_path.name.replace(".queued.json", ".running.json"))
        try:
            os.replace(queued_path, running_path)
        except FileNotFoundError:
            continue
        except OSError:
            continue

        payload = json.loads(running_path.read_text(encoding="utf-8"))
        payload["status"] = "running"
        payload["started_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(running_path, payload)

        try:
            run_deferred_maintenance_action(kb_path, str(payload["action"]), payload.get("payload", {}))
            payload["status"] = "completed"
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            payload["status"] = "failed"
            payload["error"] = str(exc)
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()

        final_suffix = ".done.json" if payload["status"] == "completed" else ".failed.json"
        final_path = running_path.with_name(running_path.name.replace(".running.json", final_suffix))
        _write_json(running_path, payload)
        os.replace(running_path, final_path)
        processed += 1

    return processed


def _resolve_submitter(kb_path: Path) -> str:
    git_user = "web-upload"
    try:
        result = subprocess.run(
            ["git", "-C", str(kb_path), "config", "user.name"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            git_user = result.stdout.strip()
    except Exception:
        pass
    return git_user


def _detect_upload_mode(filename: str, mode: str) -> str:
    if mode != "auto":
        return mode
    suffix = Path(filename).suffix.lower()
    if suffix in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        return "image"
    return "text"


def _extract_upload_modules(kb_path: Path, filename: str, payload: bytes, category: str, mode: str):
    from knowledge_manager.extractor import Extractor
    from knowledge_manager.http_server import _load_config_safe
    from knowledge_manager.llm_clients import create_client
    from knowledge_manager.storage import load_index

    cfg = _load_config_safe(kb_path)
    if cfg is None:
        raise RuntimeError("No config found")

    provider_name, provider_cfg = cfg.get_default_provider()
    client = create_client(provider_name, provider_cfg)
    extractor = Extractor(client, cfg.extraction)
    resolved_mode = _detect_upload_mode(filename, mode)

    existing_categories = ""
    if cfg.extraction.auto_categorize:
        index = load_index(kb_path)
        if index is not None and index.categories:
            existing_categories = json.dumps(
                {name: cat.description for name, cat in index.categories.items()},
                ensure_ascii=False,
            )

    async def _run():
        if resolved_mode == "image":
            tmp_dir = kb_path / ".tmp" / "worker-images"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = tmp_dir / filename
            tmp_path.write_bytes(payload)
            try:
                return await extractor.extract_from_image(str(tmp_path), category, existing_categories)
            finally:
                tmp_path.unlink(missing_ok=True)
        text = payload.decode("utf-8", errors="replace")
        return await extractor.extract(text, category, existing_categories)

    return asyncio.run(_run())


def _run_upload_job(kb_path: Path, job: IngestionJob, payload: dict[str, Any]) -> IngestionJob:
    from knowledge_manager.schemas import StagingMeta
    from knowledge_manager.storage import save_staging_meta, save_to_staging

    filename = payload.get("filename") or Path(payload.get("path", job.payload_path)).name or "upload"
    category = payload.get("category", "general")
    mode = payload.get("mode", "auto")
    if "bytes_b64" in payload:
        content = base64.b64decode(payload["bytes_b64"])
    else:
        path = Path(payload.get("path") or job.payload_path)
        content = path.read_bytes()

    update_job_stage(kb_path, job.job_id, "extracting")
    modules = _extract_upload_modules(kb_path, filename, content, category, mode)

    update_job_stage(kb_path, job.job_id, "staging")
    staging = kb_path / ".staging"
    staging.mkdir(exist_ok=True)
    submitter = _resolve_submitter(kb_path)
    for module in modules:
        save_to_staging(module, staging)
        save_staging_meta(StagingMeta(module_id=module.id, submitted_by=submitter), staging)

    store_job_result_modules(
        kb_path,
        job.job_id,
        [{"id": module.id, "category": module.category, "title": module.title} for module in modules],
    )

    path_str = payload.get("path") or job.payload_path
    if path_str:
        Path(path_str).unlink(missing_ok=True)
    return complete_ingestion_job(kb_path, job.job_id, pages_seen=1, modules_staged=len(modules))


def _run_source_sync_job(kb_path: Path, job: IngestionJob, payload: dict[str, Any]) -> IngestionJob:
    from knowledge_manager.source_ingestion import run_source_sync_once

    source_id = payload.get("source_id") or job.source_id
    update_job_stage(kb_path, job.job_id, "pulling-source")
    summary = asyncio.run(run_source_sync_once(kb_path, source_id))
    return complete_ingestion_job(
        kb_path,
        job.job_id,
        pages_seen=summary.pages_seen,
        modules_staged=summary.modules_staged,
        modules_marked_stale=summary.modules_marked_stale,
    )


def _start_job_heartbeat(kb_path: Path, job_id: str) -> tuple[Event, Thread]:
    stop_event = Event()

    def _heartbeat_loop() -> None:
        while not stop_event.wait(JOB_HEARTBEAT_INTERVAL_SECONDS):
            try:
                renew_ingestion_job_lease(kb_path, job_id, lease_seconds=JOB_LEASE_SECONDS)
            except Exception:
                return

    thread = Thread(target=_heartbeat_loop, daemon=True)
    thread.start()
    return stop_event, thread


def run_single_job(kb_path: Path, job_id: str, payload: dict[str, Any] | None = None) -> IngestionJob:
    job = load_ingestion_job(kb_path, job_id)
    if job is None:
        raise FileNotFoundError(job_id)

    effective_payload = payload or {
        "kind": job.payload_kind,
        "path": job.payload_path,
        **job.payload_meta,
    }
    job = claim_ingestion_job(kb_path, job_id, worker_id="local-worker", lease_seconds=JOB_LEASE_SECONDS)
    stop_heartbeat, heartbeat_thread = _start_job_heartbeat(kb_path, job_id)

    try:
        if effective_payload.get("kind") == "upload":
            return _run_upload_job(kb_path, job, effective_payload)
        if effective_payload.get("kind") == "source-sync":
            return _run_source_sync_job(kb_path, job, effective_payload)
        return fail_ingestion_job(kb_path, job_id, "unknown job payload")
    except Exception as exc:
        path_str = effective_payload.get("path") or job.payload_path
        if path_str and effective_payload.get("kind") == "upload":
            Path(path_str).unlink(missing_ok=True)
        return fail_ingestion_job(kb_path, job_id, str(exc))
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=0.1)
