from pathlib import Path

from knowledge_manager.ingestion_jobs import create_ingestion_job


def test_worker_run_once_drains_queued_jobs(tmp_path, monkeypatch):
    from knowledge_manager.worker_service import run_worker_loop

    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    processed_jobs = []

    monkeypatch.setattr(
        "knowledge_manager.worker_service.run_single_job",
        lambda _kb_path, job_id: processed_jobs.append(job_id),
    )

    processed = run_worker_loop(kb, once=True, poll_interval=0.01)

    assert processed >= 1
    assert processed_jobs == [job.job_id]


def test_enqueue_local_maintenance_only_queues_work(tmp_path, monkeypatch):
    from knowledge_manager.job_worker import enqueue_local_maintenance

    kb = tmp_path / "kb"
    kb.mkdir()
    started = {"count": 0}

    class ExplodingThread:
        def __init__(self, *args, **kwargs):
            started["count"] += 1
            raise AssertionError("maintenance queueing must not start a daemon thread")

    monkeypatch.setattr("knowledge_manager.job_worker.Thread", ExplodingThread)

    state = enqueue_local_maintenance(kb, action="module_saved", payload={"module_id": "ops-1"})

    assert state["deferred"] is True
    assert started["count"] == 0
    assert len(list((kb / ".cache" / "maintenance").glob("*.queued.json"))) == 1


def test_worker_run_once_drains_queued_maintenance_jobs(tmp_path, monkeypatch):
    from knowledge_manager.job_worker import enqueue_local_maintenance
    from knowledge_manager.worker_service import run_worker_loop

    kb = tmp_path / "kb"
    kb.mkdir()
    dispatched = []

    def safe_replace(src, dst):
        src_path = Path(src)
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(
        "knowledge_manager.storage.run_deferred_maintenance_action",
        lambda path, action, payload, **kwargs: dispatched.append((path, action, payload)),
    )
    monkeypatch.setattr("knowledge_manager.job_worker.os.replace", safe_replace)

    enqueue_local_maintenance(kb, action="module_saved", payload={"module_id": "ops-1"})

    processed = run_worker_loop(kb, once=True, poll_interval=0.01)

    assert processed >= 1
    assert dispatched == [(kb, "module_saved", {"module_id": "ops-1"})]
    assert len(list((kb / ".cache" / "maintenance").glob("*.done.json"))) == 1


def test_worker_batches_derived_index_rebuilds(tmp_path, monkeypatch):
    from knowledge_manager.job_worker import enqueue_local_maintenance
    from knowledge_manager.worker_service import run_worker_loop

    kb = tmp_path / "kb"
    kb.mkdir()
    dispatched = []
    rebuilds = []

    def safe_replace(src, dst):
        src_path = Path(src)
        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(
        "knowledge_manager.storage.run_deferred_maintenance_action",
        lambda path, action, payload, **kwargs: dispatched.append((path, action, payload, kwargs)),
    )
    monkeypatch.setattr(
        "knowledge_manager.job_worker.rebuild_derived_indexes",
        lambda path: rebuilds.append(path),
    )
    monkeypatch.setattr("knowledge_manager.job_worker.os.replace", safe_replace)

    enqueue_local_maintenance(kb, action="module_saved", payload={"module_id": "ops-1"})
    enqueue_local_maintenance(kb, action="module_saved", payload={"module_id": "ops-2"})

    processed = run_worker_loop(kb, once=True, poll_interval=0.01)

    assert processed >= 2
    assert len(dispatched) == 2
    assert all(item[3] == {"refresh_derived": False} for item in dispatched)
    assert rebuilds == [kb]


def test_failed_derived_rebuild_is_recorded_and_retried(tmp_path, monkeypatch):
    from knowledge_manager.derived_index_state import load_derived_index_state
    from knowledge_manager.job_worker import enqueue_local_maintenance
    from knowledge_manager.worker_service import run_worker_loop

    kb = tmp_path / "kb"
    kb.mkdir()
    calls = {"count": 0}

    def fail_once(_path):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("simulated derived rebuild failure")

    monkeypatch.setattr("knowledge_manager.storage.rebuild_derived_indexes", fail_once)
    monkeypatch.setattr(
        "knowledge_manager.storage.run_deferred_maintenance_action",
        lambda *_args, **_kwargs: None,
    )
    enqueue_local_maintenance(kb, action="module_saved", payload={"module_id": "ops-1"})
    run_worker_loop(kb, once=True, poll_interval=0.01)

    failed = load_derived_index_state(kb)
    assert failed["status"] == "failed"
    assert "simulated derived rebuild failure" in failed["last_error"]

    run_worker_loop(kb, once=True, poll_interval=0.01)
    assert load_derived_index_state(kb)["status"] == "ready"


def test_worker_skips_job_with_active_claim(tmp_path):
    from knowledge_manager.ingestion_jobs import claim_ingestion_job
    from knowledge_manager.job_worker import run_single_job

    kb = tmp_path / "kb"
    kb.mkdir()
    job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    claimed = claim_ingestion_job(kb, job.job_id, worker_id="other-worker", lease_seconds=60)

    skipped = run_single_job(kb, job.job_id, payload={"kind": "upload"})

    assert skipped.status == "running"
    assert skipped.worker_id == claimed.worker_id
