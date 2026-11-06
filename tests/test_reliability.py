import json
import multiprocessing
import os
from pathlib import Path

import pytest


def _hold_lock(kb, ready):
    from knowledge_manager.file_locks import kb_write_lock

    with kb_write_lock(Path(kb)):
        ready.set()
        while True:
            import time

            time.sleep(0.05)


def _write_modules(kb, offset):
    from knowledge_manager.schemas import Module, ModuleContent
    from knowledge_manager.storage import save_module

    for number in range(offset, offset + 4):
        save_module(
            Module(
                id=f"parallel-{number}",
                category="ops",
                title=f"Parallel module {number}",
                summary="Parallel writes must preserve every index entry.",
                content=ModuleContent(
                    overview="Concurrent writer overview.",
                    details="Concurrent writer details for durable storage.",
                ),
            ),
            Path(kb),
            defer_derived=True,
        )


def test_lock_times_out_and_recovers_after_process_death(tmp_path):
    from knowledge_manager.file_locks import kb_write_lock

    ctx = multiprocessing.get_context("spawn")
    ready = ctx.Event()
    process = ctx.Process(target=_hold_lock, args=(str(tmp_path), ready))
    process.start()
    try:
        assert ready.wait(15)
        with pytest.raises(TimeoutError):
            with kb_write_lock(tmp_path, timeout=0.1):
                pass
    finally:
        process.terminate()
        process.join(10)
    with kb_write_lock(tmp_path, timeout=2):
        pass


def test_parallel_writes_and_maintenance_preserve_all_modules(tmp_path):
    from knowledge_manager.job_worker import run_pending_maintenance
    from knowledge_manager.runtime_checks import run_integrity_check
    from knowledge_manager.storage import load_index
    from knowledge_manager.derived_index_state import load_derived_index_state

    ctx = multiprocessing.get_context("spawn")
    workers = [ctx.Process(target=_write_modules, args=(str(tmp_path), n * 4)) for n in range(3)]
    for process in workers:
        process.start()
    for process in workers:
        process.join(40)
        assert not process.is_alive()
        assert process.exitcode == 0
    index = load_index(tmp_path)
    assert len(index.categories["ops"].modules) == 12
    assert load_derived_index_state(tmp_path)["pending_operations"] == 12
    assert run_pending_maintenance(tmp_path) == 12
    assert run_integrity_check(tmp_path)["ok"]
    assert load_derived_index_state(tmp_path)["status"] == "ready"


def test_upload_failure_keeps_payload_for_successful_retry(tmp_path, monkeypatch):
    from knowledge_manager.ingestion_jobs import (
        create_ingestion_job,
        update_job_payload,
        resume_ingestion_job,
    )
    from knowledge_manager.job_worker import run_single_job
    from knowledge_manager.schemas import Module, ModuleContent

    payload = tmp_path / "input.txt"
    payload.write_text("Recoverable source document", encoding="utf-8")
    job = create_ingestion_job(tmp_path, "upload", "recovery-drill")
    update_job_payload(tmp_path, job.job_id, payload_kind="upload", payload_path=str(payload))

    def fail(*args):
        raise RuntimeError("injected extraction failure")

    monkeypatch.setattr("knowledge_manager.job_worker._extract_upload_modules", fail)
    assert run_single_job(tmp_path, job.job_id).status == "failed"
    assert payload.exists()
    module = Module(
        id="recovered",
        category="ops",
        title="Recovered upload",
        summary="Recovered upload summary text.",
        content=ModuleContent(
            overview="Recovered source overview.",
            details="Recovered source details that satisfy validation.",
        ),
    )
    monkeypatch.setattr(
        "knowledge_manager.job_worker._extract_upload_modules", lambda *args: [module]
    )
    resume_ingestion_job(tmp_path, job.job_id)
    result = run_single_job(tmp_path, job.job_id)
    assert result.status == "completed"
    assert result.attempt_count == 2
    assert len(list((tmp_path / ".staging").glob("*.json"))) >= 1
    assert not payload.exists()


def test_worker_recovers_abandoned_maintenance_claim(tmp_path):
    from knowledge_manager.job_worker import enqueue_local_maintenance, run_pending_maintenance
    from knowledge_manager.schemas import Module, ModuleContent

    module = Module(
        id="recover",
        category="ops",
        title="Recovery module",
        summary="Recovery module summary text.",
        content=ModuleContent(
            overview="Recovery module overview.",
            details="Recovery module details that satisfy validation.",
        ),
    )
    state = enqueue_local_maintenance(
        tmp_path, "module_saved", {"module": module.model_dump(mode="json"), "existed": False}
    )
    queue = tmp_path / ".cache" / "maintenance"
    queued = queue / f"{state['job_id']}.queued.json"
    payload = json.loads(queued.read_text(encoding="utf-8"))
    payload["started_at"] = "2026-01-01T00:00:00+00:00"
    queued.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(queued, queue / f"{state['job_id']}.running.json")
    assert run_pending_maintenance(tmp_path) == 1
    assert not list(queue.glob("*.running.json"))
    assert len(list(queue.glob("*.done.json"))) == 1


def _claim_job(kb, job_id, start, results):
    from knowledge_manager.ingestion_jobs import claim_ingestion_job, JobClaimConflict

    start.wait(15)
    try:
        claim_ingestion_job(Path(kb), job_id, worker_id=str(os.getpid()))
        results.put("claimed")
    except JobClaimConflict:
        results.put("conflict")


def test_concurrent_workers_claim_job_exactly_once(tmp_path):
    from knowledge_manager.ingestion_jobs import create_ingestion_job, load_ingestion_job

    job = create_ingestion_job(tmp_path, "upload", "claim-contention")
    ctx = multiprocessing.get_context("spawn")
    start = ctx.Event()
    results = ctx.Queue()
    workers = [
        ctx.Process(target=_claim_job, args=(str(tmp_path), job.job_id, start, results))
        for _ in range(4)
    ]
    try:
        for process in workers:
            process.start()
        start.set()
        for process in workers:
            process.join(30)
            assert not process.is_alive()
            assert process.exitcode == 0
        outcomes = [results.get(timeout=5) for _ in workers]
        assert outcomes.count("claimed") == 1
        assert outcomes.count("conflict") == 3
        assert load_ingestion_job(tmp_path, job.job_id).attempt_count == 1
    finally:
        for process in workers:
            if process.is_alive():
                process.terminate()
            process.join(5)
        results.close()
