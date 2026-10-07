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

## Release Evidence Verdict

- Inspect `release-support-bundle.json` before cutover and confirm `complete == true`.
- Confirm `backup_restore_drill_within_30_days == true` before cutover.
- Treat any non-empty `missing` list as a failed release-evidence gate until the absent artifact is generated or attached.

## Minimum Alerts

- readiness non-200 for 5 minutes
- metrics endpoint scrape failure for 5 minutes
- failed job count > 0
- stale running job count > 0
- disk free space below 15%
