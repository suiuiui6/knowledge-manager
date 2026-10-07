from knowledge_manager.ingestion_jobs import (
    claim_ingestion_job,
    complete_ingestion_job,
    create_ingestion_job,
    fail_ingestion_job,
    list_ingestion_jobs,
    renew_ingestion_job_lease,
    resume_ingestion_job,
    update_job_payload,
    update_ingestion_checkpoint,
    update_job_stage,
)
from datetime import datetime, timedelta, timezone
from time import sleep


def test_ingestion_job_claim_complete_round_trip(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    job = create_ingestion_job(kb, source_id="team-docs", trigger="manual")
    claimed = claim_ingestion_job(kb, job.job_id, worker_id="worker-1")
    finished = complete_ingestion_job(kb, job.job_id, pages_seen=12, modules_staged=7)

    assert claimed.status == "running"
    assert finished.status == "completed"
    assert finished.pages_seen == 12
    assert finished.modules_staged == 7


def test_ingestion_job_failure_is_listed(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    job = create_ingestion_job(kb, source_id="team-docs", trigger="manual")
    fail_ingestion_job(kb, job.job_id, "temporary failure")

    jobs = list_ingestion_jobs(kb)
    assert len(jobs) == 1
    assert jobs[0].status == "failed"
    assert jobs[0].error == "temporary failure"


def test_ingestion_job_resume_preserves_checkpoint(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="team-docs", trigger="manual")
    update_ingestion_checkpoint(kb, job.job_id, cursor="cursor-9", pages_seen=25)

    resumed = resume_ingestion_job(kb, job.job_id)

    assert resumed.resume_cursor == "cursor-9"
    assert resumed.pages_seen == 25
    assert resumed.status == "queued"


def test_job_worker_executes_upload_job_and_marks_completed(tmp_path, monkeypatch):
    from knowledge_manager.job_worker import run_single_job
    from knowledge_manager.schemas import Module, ModuleContent

    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    update_job_payload(kb, job.job_id, payload_kind="upload", payload_path=str(kb / ".tmp" / "demo.md"))

    def fake_extract(_kb_path, _filename, _payload, _category, _mode):
        return [
            Module(
                id="upload-demo",
                category="ops",
                title="Upload Demo",
                summary="Upload worker summary.",
                content=ModuleContent(
                    overview="Upload worker overview.",
                    details="Upload worker details long enough for validation.",
                ),
            )
        ]

    monkeypatch.setattr("knowledge_manager.job_worker._extract_upload_modules", fake_extract)
    finished = run_single_job(
        kb,
        job.job_id,
        payload={"kind": "upload", "filename": "demo.md", "bytes_b64": "IyB0aXRsZQ==", "category": "ops", "mode": "text"},
    )

    assert finished.status == "completed"
    assert finished.modules_staged == 1


def test_job_worker_executes_source_sync_job_and_marks_completed(tmp_path, monkeypatch):
    from knowledge_manager.job_worker import run_single_job
    from knowledge_manager.source_ingestion import IngestionSummary

    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="team-docs", trigger="manual")
    update_job_payload(kb, job.job_id, payload_kind="source-sync")

    async def fake_run_source_sync(_kb_path, source_id):
        return IngestionSummary(source_id=source_id, pages_seen=4, modules_staged=3, modules_marked_stale=1)

    monkeypatch.setattr("knowledge_manager.source_ingestion.run_source_sync_once", fake_run_source_sync)
    finished = run_single_job(
        kb,
        job.job_id,
        payload={"kind": "source-sync", "source_id": "team-docs"},
    )

    assert finished.status == "completed"
    assert finished.pages_seen == 4
    assert finished.modules_marked_stale == 1


def test_job_worker_renews_lease_while_job_runs(tmp_path, monkeypatch):
    from knowledge_manager.job_worker import run_single_job

    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    renewals = []
    real_renew = renew_ingestion_job_lease

    def tracked_renew(*args, **kwargs):
        renewals.append(args[1])
        return real_renew(*args, **kwargs)

    def slow_upload(_kb_path, claimed_job, _payload):
        sleep(0.05)
        return complete_ingestion_job(_kb_path, claimed_job.job_id, pages_seen=1, modules_staged=1)

    monkeypatch.setattr("knowledge_manager.job_worker.JOB_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr("knowledge_manager.job_worker.renew_ingestion_job_lease", tracked_renew)
    monkeypatch.setattr("knowledge_manager.job_worker._run_upload_job", slow_upload)

    finished = run_single_job(kb, job.job_id, payload={"kind": "upload"})

    assert finished.status == "completed"
    assert renewals


def test_job_worker_runs_queued_maintenance_actions(tmp_path, monkeypatch):
    from knowledge_manager.job_worker import enqueue_local_maintenance, run_pending_maintenance

    kb = tmp_path / "kb"
    kb.mkdir()
    dispatched = []

    class FakeThread:
        def __init__(self, *args, **kwargs):
            self._target = kwargs.get("target")
            self._args = kwargs.get("args", ())

        def start(self):
            return None

    monkeypatch.setattr("knowledge_manager.job_worker.Thread", FakeThread)
    monkeypatch.setattr(
        "knowledge_manager.storage.run_deferred_maintenance_action",
        lambda path, action, payload: dispatched.append((path, action, payload)),
    )

    state = enqueue_local_maintenance(kb, action="module_saved", payload={"module_id": "perf-write"})
    processed = run_pending_maintenance(kb, limit=5)

    assert state["deferred"] is True
    assert processed == 1
    assert dispatched == [(kb, "module_saved", {"module_id": "perf-write"})]
    assert len(list((kb / ".cache" / "maintenance").glob("*.done.json"))) == 1


def test_requeue_stale_running_jobs(tmp_path):
    from knowledge_manager.ingestion_jobs import load_ingestion_job
    from knowledge_manager.worker_service import requeue_stale_jobs

    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    claimed = claim_ingestion_job(kb, job.job_id, worker_id="worker-1", lease_seconds=1)
    stale = claimed.model_copy(update={"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)})
    (kb / ".jobs" / "ingestion" / f"{job.job_id}.json").write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    assert requeue_stale_jobs(kb) == [job.job_id]
    assert load_ingestion_job(kb, job.job_id).status == "queued"


def test_update_job_stage_refreshes_heartbeat_for_running_jobs(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    claimed = claim_ingestion_job(kb, job.job_id, worker_id="worker-1", lease_seconds=1)
    stale = claimed.model_copy(
        update={
            "heartbeat_at": datetime.now(timezone.utc) - timedelta(seconds=10),
            "lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=5),
        }
    )
    job_path = kb / ".jobs" / "ingestion" / f"{job.job_id}.json"
    job_path.write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    updated = update_job_stage(kb, job.job_id, "extracting")

    assert updated.stage == "extracting"
    assert updated.heartbeat_at is not None
    assert updated.lease_expires_at is not None
    assert updated.heartbeat_at > stale.heartbeat_at
    assert updated.lease_expires_at > datetime.now(timezone.utc)


def test_renew_ingestion_job_lease_refreshes_heartbeat_for_running_jobs(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()

    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    claimed = claim_ingestion_job(kb, job.job_id, worker_id="worker-1", lease_seconds=1)
    stale = claimed.model_copy(
        update={
            "heartbeat_at": datetime.now(timezone.utc) - timedelta(seconds=10),
            "lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=5),
        }
    )
    job_path = kb / ".jobs" / "ingestion" / f"{job.job_id}.json"
    job_path.write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    renewed = renew_ingestion_job_lease(kb, job.job_id, lease_seconds=60)

    assert renewed.heartbeat_at is not None
    assert renewed.lease_expires_at is not None
    assert renewed.heartbeat_at > stale.heartbeat_at
    assert renewed.lease_expires_at > datetime.now(timezone.utc)
