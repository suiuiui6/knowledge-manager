# Migration Cutover

1. Export incumbent data and run `km --kb-path <kb-path> migrate dry-run <export.json> --source-kind <kind>`.
2. Review `total_documents`, `creates`, `updates`, `skips`, and `errors` before importing anything.
3. Register enterprise connectors and run source pull jobs until `/api/source/jobs` and `km source status` stabilize.
4. Review and approve staged modules so the governed module corpus matches the incoming source set.
5. Run `km --kb-path <kb-path> eval run <suite.json>` and compare hit rate, MRR, nDCG, recall, and failure decomposition against the incumbent baseline.
6. Review `km --kb-path <kb-path> ops --format json` and `/api/admin/dashboard` for stale sources, review backlog, and ingestion job health.
7. Keep a rollback bundle containing the original export, dry-run summary, eval output, and source status snapshots before switching clients.
