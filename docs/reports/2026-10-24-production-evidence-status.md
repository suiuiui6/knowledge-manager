# Production Evidence Status — 2026-10-24

## Completed in this change

- Added cross-process KB write locking around module/index mutations, ingestion job transitions, maintenance queue operations, and derived-index state updates.
- Preserved upload payloads after extraction failure so a resumed job can retry the same input.
- Requeued abandoned maintenance claims when a worker process exits before completion.
- Added retrieval golden-set evaluation with recall, MRR, nDCG, abstention accuracy, and tenant-leakage reporting.
- Made benchmark gates fail when an iteration records an exception even if latency is low.
- Changed benchmark fixture loading to write validated module JSON and build the canonical and derived indexes once, avoiding per-module index rebuild amplification.
- Added backup manifest SHA-256 hashes, source/output path separation, restore path traversal checks, and checksum verification.
- Added a real backup/restore drill that rebuilds indexes and verifies integrity, readiness, and search overlap.

## Verification evidence

- Focused reliability, retrieval, benchmark-contract, backup, worker, and ingestion tests: `40 passed`.
- Broader storage/worker/ingestion/backup/retrieval regression set: `169 passed`.
- Backup/restore drill test produced `restore-verify-deployment.json` with successful restore, readiness, integrity, and search overlap.
- Windows subprocess tests still emit a known GBK reader warning; Windows remains `audit-only-windows`.

## Remaining gate

The fresh 50,000-module M-scale run was started locally but stopped after the file-based fixture loader demonstrated that Windows could only materialize roughly 7,000 JSON files in several minutes. The run did not produce a valid M-scale verdict. This is an evidence limitation, not a passing result. A locked Ubuntu runner must execute the M matrix before the project can claim M-scale production readiness.
