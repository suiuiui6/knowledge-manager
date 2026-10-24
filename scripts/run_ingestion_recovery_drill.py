from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from knowledge_manager.ingestion_jobs import (
    create_ingestion_job,
    resume_ingestion_job,
    update_job_payload,
)
from knowledge_manager.job_worker import run_single_job
from knowledge_manager.runtime_checks import run_integrity_check
from knowledge_manager.schemas import Index, Module, ModuleContent
from knowledge_manager.storage import save_index


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--kb-path", type=Path)
    args = parser.parse_args()
    kb = (args.kb_path or args.output.parent / "ingestion-kb").resolve()
    kb.mkdir(parents=True, exist_ok=True)
    save_index(Index(description="ingestion recovery drill"), kb)
    payload = kb / "recovery.txt"
    payload.write_text("recoverable source", encoding="utf-8")
    job = create_ingestion_job(kb, "upload", "recovery-drill")
    update_job_payload(
        kb,
        job.job_id,
        payload_kind="upload",
        payload_path=str(payload),
        payload_meta={"kind": "upload", "filename": "recovery.txt", "category": "ops"},
    )
    import knowledge_manager.job_worker as worker

    original = worker._extract_upload_modules
    worker._extract_upload_modules = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        RuntimeError("injected extraction failure")
    )
    failed = run_single_job(kb, job.job_id)
    failure_preserved = payload.exists()
    worker._extract_upload_modules = lambda *_args, **_kwargs: [
        Module(
            id="recovered",
            category="ops",
            title="Recovered",
            summary="Recovered module summary.",
            content=ModuleContent(
                overview="Recovery overview.", details="Recovery details for drill."
            ),
        )
    ]
    resume_ingestion_job(kb, job.job_id)
    completed = run_single_job(kb, job.job_id)
    worker._extract_upload_modules = original
    integrity = run_integrity_check(kb)
    report = {
        "ok": completed.status == "completed"
        and failure_preserved
        and not payload.exists()
        and integrity["ok"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "job_id": job.job_id,
        "failed_status": failed.status,
        "failure_preserved_input": failure_preserved,
        "final_status": completed.status,
        "attempt_count": completed.attempt_count,
        "integrity": integrity,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
