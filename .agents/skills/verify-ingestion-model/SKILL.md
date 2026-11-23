---
name: verify-ingestion-model
description: Verify knowledge-manager ingestion attempt ownership, terminal state preservation and periodic expired-lease recovery when ingestion_jobs, job_worker or worker_service changes.
---

# Verify ingestion model

Use `$statechart` to run and interpret `verification/ingestion/Attempts.tla` with its adjacent config and view. Resolve the supported runtime through that skill; do not copy machine-specific runtime paths into this project.

Baseline: **pending-uncommitted**. Comparison starting point: `86144a18405160bc176ee4dfe2c3fc62ededce63`. Before every run inspect committed, staged, unstaged and untracked covered changes, and directly compare model actions with source. HEAD is not a synced implementation revision. Advance the synced revision only when covered code is committed and rechecked there.

## Correspondence

- Claim: `ingestion_jobs.claim_ingestion_job`, write-lock protected read/modify/write increments attempt_count.
- Commit/Complete: `_require_attempt`, `ingestion_attempt`, `complete_ingestion_job` and local upload/source commit blocks. A stale attempt cannot write current task results.
- Expire: monotonic passage of wall time relative to lease_expires_at, abstracted as a boolean; Heartbeat preserves an already valid lease and cannot revive an expired attempt.
- Scan/Recover: `worker_service.requeue_stale_jobs`, `requeue_expired_ingestion_job`; recovery rechecks status, attempt and lease under the same KB lock.
- CompletedDoesNotRegress: completed jobs reject claim, resume and attempt-bound late failure.

Bounds: one persistent job, two attempts, arbitrary interleavings. Atomic actions correspond to KB write-lock regions. Fair scanning/recovery is assumed for liveness; process scheduling fairness and continued worker operation are assumptions. Deadlock checking is disabled because the bounded queued state can stop at MaxAttempts; this is not a proof of implementation deadlock freedom. External extraction, exact-once provider invocation, multi-file crash durability, retry limits and complete application correctness are excluded. Automatic recovery may retry indefinitely under the existing policy; this model does not claim eventual successful completion.

## Checks and evidence

Run `$statechart` with a new evidence folder under `test-results/ingestion-model/`, then read report.md and tlc.out, including unchecked properties. Include the generated chart.mmd and explain any omitted steps. Run real behavior regressions as well:

```text
poetry run pytest -q tests/test_ingestion_jobs.py tests/test_worker_service.py tests/test_reliability.py tests/test_source_ingestion.py
```

Negative controls: on scratch copies set BrokenAttemptGuard, BrokenRecovery and BrokenTerminalGuard true separately; expect the ownership invariant, recovery liveness and terminal invariant respectively to fail. Never change the real config to suppress a finding. Replay counterexamples against real APIs in temporary KBs; mutations of real source must be isolated in disposable copies, never shared active files. A model-only negative control is insufficient to claim source mutation sensitivity.

Unexecuted or insufficiently mapped checks are drafts. Preserve evidence on cleanup. Use `$maintain-formal-verification-skill` after changes affecting these contracts.
