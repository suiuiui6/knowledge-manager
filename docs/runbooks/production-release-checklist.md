# Production Release Checklist

## Goal

Use this checklist before declaring the current single-node `knowledge-manager` deployment production-ready.

The current repository may be called production-grade only when all of the following are true:

1. `km verify-production-readiness` passes on a fresh matrix summary.
2. `km verify-deployment` passes against the running service.
3. `km support bundle` has been generated for the release and stored with the release record.
4. The monthly backup/restore drill has passed within the last 30 days.
5. TLS termination, service supervision, and log retention config are installed from the checked-in deploy artifacts.

## Pre-Release Checks

1. Run deterministic regression tests for search, recommendations, jobs, runtime checks, HTTP, MCP, and write paths.
2. Run `km integrity --format json` and confirm `ok == true`.
3. Verify `GET /api/ready` returns HTTP `200`.
4. Verify `GET /api/metrics` returns Prometheus text without server errors.
5. Confirm no ingestion jobs are stuck in `failed` state unexpectedly.
6. Run `python scripts/verify_install_smoke.py` from the repo root and confirm the wheel build, clean venv install, `km init`, `km stats`, and invalid-runtime-env checks all pass.

## Production Release Sequencing

1. Land the Task 1-4 production blockers first and deploy with `production_mode=false` and `multi_tenant_mode=false`.
2. Configure auth claims for `user`, `tenant_id`, and `workspace_id`, then confirm the tenant-scoped HTTP and MCP checks pass with real tokens.
3. In any multi-tenant environment, disable MCP global resources before exposing MCP to non-admin consumers.
4. If `/api/upload` or source sync will be enabled, start `km worker run` under a real service manager and confirm stale jobs can be requeued and the queue drains normally.
5. Create a release evidence directory for the cutover record:

   ```bash
   RELEASE_DIR=/opt/knowledge-manager/release-artifacts/run-$(date +%Y%m%d%H%M%S)
   install -d -o km -g km "$RELEASE_DIR"
   ```

6. Run `python3.11 /opt/knowledge-manager/scripts/verify_install_smoke.py --project-root /opt/knowledge-manager --python python3.11 --format json > "$RELEASE_DIR"/verify-install-smoke.json`.
7. Run `/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-production-readiness --matrix-summary <fresh-matrix-summary.json> > "$RELEASE_DIR"/verify-production-readiness.json`.
8. Run `/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json > "$RELEASE_DIR"/verify-deployment.json`.
9. Run `python3.11 /opt/knowledge-manager/scripts/collect_release_evidence.py --release-dir "$RELEASE_DIR" --kb-path /opt/knowledge-manager/kb --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json>` as the preferred cutover gate. This command regenerates `verify-production-readiness.json`, `verify-deployment.json`, `release-support-bundle.json`, captures host deploy proof, writes `verify-release-artifacts.json`, and persists `release-evidence-collection.json`.
10. If you need to inspect or rerun the stages individually, generate `/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb support bundle --output-dir "$RELEASE_DIR" --matrix-summary <fresh-matrix-summary.json>` and then run `python3.11 /opt/knowledge-manager/scripts/verify_release_artifacts.py --release-dir "$RELEASE_DIR"`.
11. Confirm the final release packet still satisfies `complete == true`, `missing == []`, `backup_restore_drill_within_30_days == true`, `deploy_artifact_proof_complete == true`, and `host_deploy_proof_path` pointing to `"$RELEASE_DIR"/host-deploy-proof.json`.
12. Only enable `production_mode=true` after readiness, integrity, deployment verification, support bundle generation, and all required performance scales pass.

## Coverage Alignment

- Task 6 governance depends on Task 1-4 already being in place: fail-closed auth and RBAC, auth-derived tenant scope, MCP resource lockdown, and truthful readiness with multi-scale verification.
- Treat Task 5 as mandatory before cutover whenever production will expose `/api/upload` or source sync.

## Benchmark Evidence

1. Run the benchmark contract suite in `tests/test_performance_benchmarks.py`.
2. Run the production matrix for `xs`, `s`, and `m` scales.
3. Confirm each benchmark artifact includes:
   - `gate_summary`
   - `release_verdict`
4. Only declare production-ready when `release_verdict.ready_for_production == true` for the fresh gate run you are using as evidence.

## Rollback Triggers

- Any cross-tenant leakage in search or HTTP results
- Any failed integrity check after rollout
- Three consecutive upload/source jobs ending in `failed`
- `release_verdict.ready_for_production == false` on the validation matrix
- Readiness endpoint returning `503` in production

## Rollback Rules

1. If the cutover fails before `production_mode=true`, roll back the code or configuration change that introduced the failure and keep the environment in the staged pre-cutover configuration.
2. If the cutover fails after `production_mode=true`, revert the release artifact or configuration first; do not treat leaving `production_mode` disabled long-term as a steady-state operating model.
3. After rollback, re-run readiness and integrity checks before re-opening traffic.
4. If jobs were left in `running`, `queued`, or stale lease states, recover them with the worker service before retrying deployment.
5. For upload or source-sync incidents, verify queue recovery explicitly by running `/opt/knowledge-manager/.venv/bin/km worker run --once` or the equivalent managed worker recovery workflow.

## Reload

```bash
systemctl daemon-reload
systemctl restart knowledge-manager-api
systemctl restart knowledge-manager-worker
/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json
```

## Rollback Procedure

```bash
systemctl stop knowledge-manager-api
systemctl stop knowledge-manager-worker
mv /opt/knowledge-manager/kb /opt/knowledge-manager/kb.rollback.$(date +%Y%m%d%H%M%S)
install -d -o km -g km /opt/knowledge-manager/kb
/opt/knowledge-manager/.venv/bin/km backup restore --bundle <known-good-backup.zip> --target-kb /opt/knowledge-manager/kb
systemctl start knowledge-manager-api
systemctl start knowledge-manager-worker
/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json
```

## Repair Actions

1. Run `km integrity --repair`.
2. Re-run benchmark gates for the affected scale.
3. Re-check `/api/ready`, `/api/metrics`, and `/api/source/jobs`.
