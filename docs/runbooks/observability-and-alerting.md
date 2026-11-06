# Minimum Verifiable Observability Baseline

## Minimum Verified Surfaces

- `curl -fsS http://127.0.0.1:8420/api/ready`
- `curl -fsS http://127.0.0.1:8420/api/metrics`
- `km --kb-path <kb> verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json`
- `km --kb-path <kb> support bundle --output-dir <dir> --matrix-summary <fresh-matrix-summary.json>`

## Log Locations

- audit log: `kb/.audit/audit.jsonl`
- telemetry dir: `kb/.telemetry/`
- job state dir: `kb/.jobs/`
- service logs: journald or `/var/log/knowledge-manager/*.log`
- support bundle artifact: `release-support-bundle.json`
- derived index state: `kb/.cache/derived-index-state.json`

## Release Evidence Verdict

- Inspect `release-support-bundle.json` before cutover and confirm `complete == true`.
- Confirm `backup_restore_drill_within_30_days == true` before cutover.
- Treat any non-empty `missing` list as a failed release-evidence gate until the absent artifact is generated or attached.

## Minimum Alerts

- readiness non-200 for 5 minutes
- metrics endpoint scrape failure for 5 minutes
- failed job count > 0
- stale running job count > 0
- derived index state is `failed` or remains `dirty` while the maintenance worker is expected to run
- disk free space below 15%

## Derived index maintenance

Primary module JSON and the canonical module index are written before derived indexes. Writes record a dirty generation in `derived-index-state.json` and queue maintenance work. The worker batches queued module saves and deletes, rebuilds the lexical, search projection, and recommendation indexes once, and then records `status=ready` with `last_success_at`.

If a rebuild fails, the state records `status=failed`, `last_error`, and `retry_count`. Run the managed worker again after correcting the underlying failure; a dirty or failed state keeps readiness from passing until the rebuild succeeds. The Prometheus endpoint exposes `knowledge_manager_derived_index_pending_operations` for backlog alerting.
