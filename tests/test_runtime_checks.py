from datetime import datetime, timedelta, timezone

from knowledge_manager.schemas import Index, Module, ModuleContent
from knowledge_manager.storage import save_index, save_module


def test_evaluate_readiness_reports_default_provider_error(tmp_path):
    from knowledge_manager.runtime_checks import evaluate_readiness

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="ready"), kb)
    (kb / "config.json").write_text('{"llm_providers": {}}', encoding="utf-8")

    state = evaluate_readiness(kb)

    assert state["ready"] is False
    assert any("default provider" in reason.lower() for reason in state["reasons"])


def test_evaluate_readiness_fails_on_failed_ingestion_jobs(tmp_path):
    from knowledge_manager.ingestion_jobs import create_ingestion_job
    from knowledge_manager.runtime_checks import evaluate_readiness

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="ready"), kb)
    (kb / "config.json").write_text(
        '{"llm_providers": {"x": {"api_key": "k", "model": "m", "default": true}}}',
        encoding="utf-8",
    )

    failed_job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    job_path = kb / ".jobs" / "ingestion" / f"{failed_job.job_id}.json"
    payload = job_path.read_text(encoding="utf-8").replace('"status": "queued"', '"status": "failed"').replace('"stage": "queued"', '"stage": "failed"')
    job_path.write_text(payload, encoding="utf-8")

    state = evaluate_readiness(kb)

    assert state["ready"] is False
    assert any("failed ingestion job" in reason.lower() for reason in state["reasons"])


def test_evaluate_readiness_fails_on_stale_running_ingestion_jobs(tmp_path):
    from knowledge_manager.ingestion_jobs import claim_ingestion_job, create_ingestion_job
    from knowledge_manager.runtime_checks import evaluate_readiness

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="ready"), kb)
    (kb / "config.json").write_text(
        '{"llm_providers": {"x": {"api_key": "k", "model": "m", "default": true}}}',
        encoding="utf-8",
    )

    running_job = create_ingestion_job(kb, source_id="upload", trigger="http-upload")
    claimed = claim_ingestion_job(kb, running_job.job_id, worker_id="worker-1", lease_seconds=60)
    job_path = kb / ".jobs" / "ingestion" / f"{claimed.job_id}.json"
    stale = claimed.model_copy(update={"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)})
    job_path.write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    state = evaluate_readiness(kb)

    assert state["ready"] is False
    assert any("stale running ingestion job" in reason.lower() for reason in state["reasons"])


def test_evaluate_readiness_reports_maintenance_backlog_thresholds(tmp_path):
    from knowledge_manager.runtime_checks import evaluate_readiness

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="ready"), kb)
    (kb / "config.json").write_text(
        '{"llm_providers": {"x": {"api_key": "k", "model": "m", "default": true}}, "security": {"maintenance_backlog_warn": 1, "maintenance_backlog_fail": 2}}',
        encoding="utf-8",
    )
    queue_dir = kb / ".cache" / "maintenance"
    queue_dir.mkdir(parents=True)
    (queue_dir / "job-1.queued.json").write_text('{"job_id": "job-1"}', encoding="utf-8")

    degraded = evaluate_readiness(kb)

    assert degraded["ready"] is True
    assert degraded["status"] == "degraded"
    assert any("maintenance backlog" in warning.lower() for warning in degraded["warnings"])

    (queue_dir / "job-2.queued.json").write_text('{"job_id": "job-2"}', encoding="utf-8")

    failed = evaluate_readiness(kb)

    assert failed["ready"] is False
    assert failed["status"] == "fail"
    assert any("maintenance backlog" in reason.lower() for reason in failed["reasons"])


def test_integrity_check_reports_missing_index_entry(tmp_path):
    from knowledge_manager.runtime_checks import run_integrity_check

    kb = tmp_path / "kb"
    kb.mkdir()
    save_module(
        Module(
            id="orphan",
            category="ops",
            title="Orphan Module",
            summary="Orphan module summary.",
            content=ModuleContent(
                overview="Orphan module overview.",
                details="Orphan module details long enough for validation.",
            ),
        ),
        kb,
    )
    (kb / "index.json").unlink(missing_ok=True)

    report = run_integrity_check(kb)

    assert report["issues"]
    assert any("index" in issue["kind"] for issue in report["issues"])


def test_collect_runtime_metrics_includes_job_and_module_counts(tmp_path):
    from knowledge_manager.ingestion_jobs import create_ingestion_job
    from knowledge_manager.runtime_checks import collect_runtime_metrics

    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="metrics"), kb)
    save_module(
        Module(
            id="metrics-module",
            category="ops",
            title="Metrics Module",
            summary="Metrics module summary.",
            content=ModuleContent(
                overview="Metrics module overview.",
                details="Metrics module details long enough for validation.",
            ),
        ),
        kb,
    )
    create_ingestion_job(kb, source_id="upload", trigger="http-upload")

    snapshot = collect_runtime_metrics(kb)

    assert "knowledge_manager_modules_total 1" in snapshot
    assert 'knowledge_manager_ingestion_jobs_total{status="queued"} 1' in snapshot
