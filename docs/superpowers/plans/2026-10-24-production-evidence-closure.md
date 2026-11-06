# Production Evidence and Reliability Implementation Plan

> **For agentic workers:** Execute each task with test-first verification and keep each task independently reviewable.

**Goal:** Complete M-scale performance evidence, retrieval quality benchmarking, ingestion recovery validation, concurrent write protection, and backup/restore evidence for the current file-based architecture.

**Architecture:** Keep the existing JSON module and derived-index design. Add evidence-producing harnesses and focused reliability primitives rather than introducing GraphRAG, a database, or distributed services. Protect primary and queue state with cross-process lock files, validate recovery through real state transitions, and make release artifacts machine-readable.

**Tech Stack:** Python 3.10+, Pydantic, pytest, Poetry lockfile, existing benchmark and backup tooling.

---

### Task 1: Freeze baseline and evidence layout

**Files:**
- Create: `docs/reports/2026-10-24-production-evidence-status.md`
- Test: existing benchmark, retrieval, ingestion, and backup suites

- [ ] Record current commit, CI run, known M-scale failures, and Windows audit-only limitation.
- [ ] Define output directories for matrix summaries, retrieval quality reports, recovery drills, concurrency drills, and backup restore drills.
- [ ] Run focused existing tests and save exit codes before code changes.

### Task 2: Add retrieval quality golden-set evaluator

**Files:**
- Create: `scripts/run_retrieval_quality.py`
- Create: `tests/test_retrieval_quality.py`
- Modify: `src/knowledge_manager/retrieval_eval.py`

- [ ] Write failing tests for loading cases, scoring recall/MRR/nDCG, tenant leakage, and report serialization.
- [ ] Implement a JSON golden-set format with query, required module keys, tenant/workspace scope, and top-k.
- [ ] Evaluate storage search and emit machine-readable aggregate metrics.
- [ ] Run the evaluator against a deterministic fixture and record baseline metrics.

### Task 3: Complete M-scale benchmark evidence

**Files:**
- Modify: `src/knowledge_manager/performance_benchmarks.py`
- Create: `scripts/run_production_matrix.py`
- Create: `tests/test_production_matrix.py`

- [ ] Add an explicit M profile command that produces fresh raw and summary artifacts.
- [ ] Ensure failed gates, readiness, integrity, and benchmark verdict are all preserved.
- [ ] Add freshness checks so old matrix artifacts cannot satisfy a new release.
- [ ] Run XS/S/M under the locked Ubuntu environment; keep Windows results audit-only.

### Task 4: Validate ingestion failure and recovery behavior

**Files:**
- Create: `scripts/run_ingestion_recovery_drill.py`
- Create: `tests/test_ingestion_recovery_drill.py`
- Modify: `src/knowledge_manager/ingestion_jobs.py`
- Modify: `src/knowledge_manager/job_worker.py`

- [ ] Write failing tests for stale lease requeue, checkpoint preservation, retry limits, failed maintenance recovery, and final module/index consistency.
- [ ] Implement only missing recovery semantics, preserving current job schema and worker entry points.
- [ ] Emit a drill artifact with injected failure, recovery action, final state, and integrity/readiness result.
- [ ] Run the drill using real temporary KB state.

### Task 5: Add cross-process write protection

**Files:**
- Create: `src/knowledge_manager/file_locks.py`
- Create: `tests/test_file_locks.py`
- Modify: `src/knowledge_manager/storage.py`
- Modify: `src/knowledge_manager/ingestion_jobs.py`
- Modify: `src/knowledge_manager/job_worker.py`

- [ ] Write failing multiprocessing tests proving concurrent module writes and queue claims do not corrupt state or duplicate claims.
- [ ] Add a bounded cross-platform lock-file helper with stale-owner cleanup and timeout errors.
- [ ] Guard compound module/index/derived-state mutations and job state transitions.
- [ ] Run concurrent stress tests and verify JSON parseability plus integrity.

### Task 6: Execute and record backup/restore drill

**Files:**
- Create: `scripts/run_backup_restore_drill.py`
- Create: `tests/test_backup_restore_drill.py`
- Modify: `src/knowledge_manager/backup_restore.py`
- Modify: `docs/runbooks/backup-restore-drill.md`

- [ ] Write failing tests requiring restored module data, config/auth, operational state, derived-index rebuild, and post-restore search.
- [ ] Implement missing manifest validation or restore verification only where tests demonstrate a gap.
- [ ] Run backup, restore into an empty directory, rebuild derived indexes, and verify readiness/integrity/search.
- [ ] Emit `restore-verify-deployment.json` with source, target, commit, checks, and timestamps.

### Task 7: Final verification and release evidence

**Files:**
- Modify: `docs/reports/2026-10-24-production-evidence-status.md`

- [ ] Run focused tests, full Ubuntu CI, and all five evidence drills.
- [ ] Attach fresh artifacts to the release support bundle.
- [ ] Report modified, verified, committed, deployed, failed, and blocked items separately.
- [ ] Do not mark production-ready unless M gates, retrieval quality, recovery, concurrency, and restore checks all pass.
