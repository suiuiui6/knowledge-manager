from knowledge_manager.ingestion_jobs import (
    claim_ingestion_job,
    complete_ingestion_job,
    create_ingestion_job,
    fail_ingestion_job,
    list_ingestion_jobs,
    resume_ingestion_job,
    update_ingestion_checkpoint,
)


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
