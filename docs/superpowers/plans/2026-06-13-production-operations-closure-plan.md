# Production Operations Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining production-operations gaps in `knowledge-manager` so the current single-node build is not only benchmark-green, but also deployable, recoverable, observable, and governable in day-2 operations.

**Architecture:** Keep the current single-node, file-backed architecture and treat the application layer as substantially ready. This plan does not reopen core retrieval or tenant-path performance work. Instead, it adds the missing operational closure around deployment, secret/config injection, backup and restore, logging and alerting integration, and cutover/rollback governance.

**Tech Stack:** Python 3.10+, Click CLI, FastAPI, Uvicorn, systemd, Caddy or Nginx for TLS termination, pytest, JSON/JSONL artifacts, runbooks under `docs/runbooks/`.

---

## Current State This Plan Assumes

The current repository already has application-level production evidence:

- `xs`, `s`, and `m` production-gate matrix entries are currently green in `test-results/perf-run-production-gate-20260613-r16-matrix-summary.json`
- readiness, integrity, audit, worker-loop, and release-verification code already exist
- production release and performance runbooks already exist in `docs/runbooks/`

This plan therefore assumes the remaining work is operational, not retrieval-algorithmic:

- no canonical deployment unit files or reverse-proxy config are checked in
- no example production environment contract is checked in
- no first-class backup/restore scripts or drill tests are checked in
- no log retention or service-manager guidance is checked in
- no operator command bundles health, readiness, integrity, and deployment evidence into one release-support artifact

## File Structure

### Existing files to extend

- `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
  Responsibility: operator commands and release-support commands.
- `D:\tyh\knowledge-manager\tests\test_cli.py`
  Responsibility: CLI behavior verification.
- `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
  Responsibility: final release, cutover, rollback, and operator procedure.
- `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`
  Responsibility: benchmark evidence and release-gate interpretation.
- `D:\tyh\knowledge-manager\README.md`
  Responsibility: top-level operator onboarding and deployment entry points.

### New files to create

- `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service`
  Responsibility: supervised API startup.
- `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service`
  Responsibility: supervised worker startup.
- `D:\tyh\knowledge-manager\deploy\caddy\Caddyfile`
  Responsibility: TLS termination and reverse proxy example.
- `D:\tyh\knowledge-manager\deploy\logrotate\knowledge-manager`
  Responsibility: JSONL audit / app log retention example.
- `D:\tyh\knowledge-manager\.env.production.example`
  Responsibility: documented production environment variable contract.
- `D:\tyh\knowledge-manager\scripts\backup_kb.py`
  Responsibility: create timestamped backup bundles for the KB, audit logs, jobs, and config.
- `D:\tyh\knowledge-manager\scripts\restore_kb.py`
  Responsibility: restore a backup bundle into a target KB path safely.
- `D:\tyh\knowledge-manager\tests\test_backup_restore.py`
  Responsibility: backup/restore round-trip and guardrail verification.
- `D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md`
  Responsibility: operational drill procedure and acceptance rules.
- `D:\tyh\knowledge-manager\docs\runbooks\observability-and-alerting.md`
  Responsibility: logs, metrics, alerts, and capacity watchpoints.

## Delivery Stages

1. `P0` Check in deployable service-manager, TLS, and environment examples
2. `P0` Add tested backup/restore tooling and drill documentation
3. `P0` Add observable operations guidance and a release-support bundle command
4. `P1` Harden release governance with rollback, retention, and evidence freshness rules

### Task 1: Check In Production Deployment Artifacts

**Files:**
- Create: `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service`
- Create: `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service`
- Create: `D:\tyh\knowledge-manager\deploy\caddy\Caddyfile`
- Create: `D:\tyh\knowledge-manager\.env.production.example`
- Modify: `D:\tyh\knowledge-manager\README.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`

- [ ] **Step 1: Write the deployment artifact tests as documentation assertions**

```python
from pathlib import Path


def test_production_artifacts_exist():
    root = Path(__file__).resolve().parents[1]
    assert (root / "deploy" / "systemd" / "knowledge-manager-api.service").exists()
    assert (root / "deploy" / "systemd" / "knowledge-manager-worker.service").exists()
    assert (root / "deploy" / "caddy" / "Caddyfile").exists()
    assert (root / ".env.production.example").exists()


def test_readme_mentions_deploy_entrypoints():
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "deploy/systemd/knowledge-manager-api.service" in readme
    assert "deploy/caddy/Caddyfile" in readme
```

- [ ] **Step 2: Run the focused artifact tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "production_artifacts_exist or deploy_entrypoints" -q`

Expected: `FAIL` because these files and references do not exist yet.

- [ ] **Step 3: Add the API service unit**

```ini
[Unit]
Description=knowledge-manager API
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=km
Group=km
WorkingDirectory=/opt/knowledge-manager
EnvironmentFile=/opt/knowledge-manager/.env.production
ExecStart=/opt/knowledge-manager/.venv/bin/uvicorn knowledge_manager.http_server:create_app --factory --host 127.0.0.1 --port 8000 --workers 2
Restart=always
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: Add the worker service unit and TLS proxy example**

```ini
[Unit]
Description=knowledge-manager worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=km
Group=km
WorkingDirectory=/opt/knowledge-manager
EnvironmentFile=/opt/knowledge-manager/.env.production
ExecStart=/opt/knowledge-manager/.venv/bin/km --kb /opt/knowledge-manager/kb worker run --poll-interval 1.0
Restart=always
RestartSec=5
TimeoutStopSec=30
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```caddy
km.example.com {
    encode gzip zstd
    reverse_proxy 127.0.0.1:8000
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "no-referrer"
    }
}
```

- [ ] **Step 5: Add the production environment contract**

```dotenv
KM_KB_PATH=/opt/knowledge-manager/kb
KM_HOST=127.0.0.1
KM_PORT=8000
KM_LOG_LEVEL=INFO
KM_AUDIT_LOG_DIR=/opt/knowledge-manager/kb/.audit
KM_PRODUCTION_MODE=true
KM_MULTI_TENANT_MODE=true
KM_MCP_GLOBAL_RESOURCES=disabled
OPENAI_API_KEY=replace-me
```

- [ ] **Step 6: Document exact deployment steps in README and the release checklist**

```markdown
## Production Deployment

1. Copy `.env.production.example` to `.env.production` and inject real secrets through your secret-management path.
2. Install `deploy/systemd/knowledge-manager-api.service` and `deploy/systemd/knowledge-manager-worker.service`.
3. Install `deploy/caddy/Caddyfile` or translate it to your reverse proxy.
4. Start the API unit.
5. Start the worker unit if uploads or source sync are enabled.
6. Run `km verify-production-readiness` before exposing traffic.
```

- [ ] **Step 7: Re-run the artifact tests**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "production_artifacts_exist or deploy_entrypoints" -q`

Expected: `PASS`.

- [ ] **Step 8: Commit**

```bash
git add D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service D:\tyh\knowledge-manager\deploy\caddy\Caddyfile D:\tyh\knowledge-manager\.env.production.example D:\tyh\knowledge-manager\README.md D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md D:\tyh\knowledge-manager\tests\test_cli.py
git commit -m "ops: add production deployment artifacts"
```

### Task 2: Add Tested Backup And Restore Tooling

**Files:**
- Create: `D:\tyh\knowledge-manager\scripts\backup_kb.py`
- Create: `D:\tyh\knowledge-manager\scripts\restore_kb.py`
- Create: `D:\tyh\knowledge-manager\tests\test_backup_restore.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md`

- [ ] **Step 1: Write the failing backup/restore tests**

```python
from pathlib import Path

from knowledge_manager.schemas import Index
from knowledge_manager.storage import save_index


def test_backup_script_creates_bundle_with_kb_and_audit(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="backup"), kb)
    (kb / ".audit").mkdir()
    (kb / ".audit" / "audit.jsonl").write_text('{"ok":true}\n', encoding="utf-8")

    from scripts.backup_kb import create_backup_bundle

    bundle = create_backup_bundle(kb, tmp_path / "backups")
    assert bundle.exists()
    assert bundle.suffix == ".zip"


def test_restore_script_recreates_index_file(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="restore"), kb)

    from scripts.backup_kb import create_backup_bundle
    from scripts.restore_kb import restore_backup_bundle

    bundle = create_backup_bundle(kb, tmp_path / "backups")
    restored = tmp_path / "restored-kb"
    restore_backup_bundle(bundle, restored)

    assert (restored / "index.json").exists()
```

- [ ] **Step 2: Run the backup/restore tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src;D:\tyh\knowledge-manager'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_backup_restore.py -q`

Expected: `FAIL` because the scripts and CLI wrappers do not exist yet.

- [ ] **Step 3: Implement the backup script**

```python
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def create_backup_bundle(kb_path: Path, output_dir: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    staging_dir = output_dir / f"knowledge-manager-backup-{timestamp}"
    staging_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(kb_path, staging_dir / "kb")
    manifest = {
        "created_at": timestamp,
        "source_kb_path": str(kb_path),
        "contents": ["kb"],
    }
    (staging_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    archive_base = output_dir / f"knowledge-manager-backup-{timestamp}"
    archive = shutil.make_archive(str(archive_base), "zip", root_dir=staging_dir.parent, base_dir=staging_dir.name)
    shutil.rmtree(staging_dir)
    return Path(archive)
```

- [ ] **Step 4: Implement the restore script with target-path guardrails**

```python
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path


def restore_backup_bundle(bundle_path: Path, target_kb_path: Path) -> None:
    if target_kb_path.exists() and any(target_kb_path.iterdir()):
        raise ValueError(f"restore target must be empty: {target_kb_path}")
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        shutil.unpack_archive(str(bundle_path), str(tmp_root))
        extracted = next(tmp_root.iterdir())
        manifest = json.loads((extracted / "manifest.json").read_text(encoding="utf-8"))
        if "kb" not in manifest.get("contents", []):
            raise ValueError("backup bundle missing kb payload")
        shutil.copytree(extracted / "kb", target_kb_path, dirs_exist_ok=True)
```

- [ ] **Step 5: Add CLI wrappers and the backup/restore drill runbook**

```python
@cli.group("backup")
def backup() -> None:
    """Backup and restore knowledge base data."""


@backup.command("create")
@click.option("--output-dir", type=click.Path(path_type=Path), required=True)
@click.pass_context
def backup_create(ctx: click.Context, output_dir: Path) -> None:
    from scripts.backup_kb import create_backup_bundle
    bundle = create_backup_bundle(ctx.obj["kb_path"], output_dir)
    click.echo(str(bundle))


@backup.command("restore")
@click.option("--bundle", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--target-kb", type=click.Path(path_type=Path), required=True)
def backup_restore(bundle: Path, target_kb: Path) -> None:
    from scripts.restore_kb import restore_backup_bundle
    restore_backup_bundle(bundle, target_kb)
    click.echo(str(target_kb))
```

```markdown
## Backup And Restore Drill

1. Create a fresh bundle with `km --kb <kb> backup create --output-dir <dir>`.
2. Restore into an empty sibling path.
3. Run `km --kb <restored-kb> integrity --format json`.
4. Run `km --kb <restored-kb> verify-production-readiness --matrix-summary <fresh-summary>`.
5. Only accept the drill if both commands succeed and audit logs remain readable.
```

- [ ] **Step 6: Re-run the backup/restore tests**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src;D:\tyh\knowledge-manager'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_backup_restore.py D:\tyh\knowledge-manager\tests\test_cli.py -k "backup or restore" -q`

Expected: `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\scripts\backup_kb.py D:\tyh\knowledge-manager\scripts\restore_kb.py D:\tyh\knowledge-manager\tests\test_backup_restore.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md D:\tyh\knowledge-manager\tests\test_cli.py
git commit -m "ops: add backup and restore tooling"
```

### Task 3: Add Log Retention And Observability Guidance

**Files:**
- Create: `D:\tyh\knowledge-manager\deploy\logrotate\knowledge-manager`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\observability-and-alerting.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- Modify: `D:\tyh\knowledge-manager\README.md`

- [ ] **Step 1: Write the observability documentation assertions**

```python
from pathlib import Path


def test_observability_runbook_mentions_metrics_alerts_and_logs():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "runbooks" / "observability-and-alerting.md").read_text(encoding="utf-8")
    assert "/api/metrics" in text
    assert "audit.jsonl" in text
    assert "alert" in text.lower()
    assert "logrotate" in text.lower()
```

- [ ] **Step 2: Run the observability assertions and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "observability_runbook_mentions_metrics_alerts_and_logs" -q`

Expected: `FAIL`.

- [ ] **Step 3: Add logrotate policy**

```conf
/opt/knowledge-manager/kb/.audit/audit.jsonl
/var/log/knowledge-manager/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
    copytruncate
}
```

- [ ] **Step 4: Add the observability and alerting runbook**

```markdown
# Observability And Alerting

## Signals

- `GET /api/health`
- `GET /api/ready`
- `GET /api/metrics`
- audit log at `kb/.audit/audit.jsonl`
- worker status via `systemctl status knowledge-manager-worker`

## Minimum Alerts

- readiness returns non-200 for 5 minutes
- integrity check fails
- worker service is down while uploads or source sync are enabled
- failed ingestion jobs count > 0
- stale running ingestion jobs count > 0
- disk free space below 15%

## Log Retention

- rotate JSONL audit and application logs daily
- retain at least 14 compressed generations
- ship logs to the central sink if one exists
```

- [ ] **Step 5: Link the observability runbook from README and the release checklist**

```markdown
- Review `docs/runbooks/observability-and-alerting.md` before production cutover.
- Confirm `/api/metrics` is scraped and alert rules are installed.
```

- [ ] **Step 6: Re-run the observability assertions**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "observability_runbook_mentions_metrics_alerts_and_logs" -q`

Expected: `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\deploy\logrotate\knowledge-manager D:\tyh\knowledge-manager\docs\runbooks\observability-and-alerting.md D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md D:\tyh\knowledge-manager\README.md D:\tyh\knowledge-manager\tests\test_cli.py
git commit -m "ops: add observability and log retention guidance"
```

### Task 4: Add A Release-Support Evidence Bundle Command

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`

- [ ] **Step 1: Write the failing CLI test for the evidence bundle**

```python
def test_support_bundle_writes_release_evidence(tmp_path, runner):
    from knowledge_manager.cli import cli

    kb = tmp_path / "kb"
    kb.mkdir()
    out = tmp_path / "bundle"

    result = runner.invoke(
        cli,
        ["--kb", str(kb), "support", "bundle", "--output-dir", str(out), "--matrix-summary", str(tmp_path / "matrix-summary.json")],
    )

    assert result.exit_code == 0
    assert any(path.name.endswith(".json") for path in out.iterdir())
```

- [ ] **Step 2: Run the focused CLI test and verify it fails**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "support_bundle_writes_release_evidence" -q`

Expected: `FAIL`.

- [ ] **Step 3: Add the CLI group and bundle command**

```python
@cli.group("support")
def support() -> None:
    """Generate operator support artifacts."""


@support.command("bundle")
@click.option("--output-dir", type=click.Path(path_type=Path), required=True)
@click.option("--matrix-summary", type=click.Path(path_type=Path, exists=True), required=True)
@click.pass_context
def support_bundle(ctx: click.Context, output_dir: Path, matrix_summary: Path) -> None:
    from datetime import datetime, timezone
    from knowledge_manager.performance_benchmarks import build_production_readiness_verdict
    from knowledge_manager.runtime_checks import evaluate_readiness, run_integrity_check

    output_dir.mkdir(parents=True, exist_ok=True)
    kb = ctx.obj["kb_path"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "kb_path": str(kb),
        "readiness": evaluate_readiness(kb),
        "integrity": run_integrity_check(kb),
        "production_verdict": build_production_readiness_verdict(kb, matrix_summary),
    }
    path = output_dir / "release-support-bundle.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(str(path))
```

- [ ] **Step 4: Document when to generate the support bundle**

```markdown
Before cutover and after rollback, generate a release-support bundle:

```powershell
km --kb <kb> support bundle --output-dir <dir> --matrix-summary <fresh-matrix-summary.json>
```
```

- [ ] **Step 5: Re-run the CLI bundle test**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "support_bundle_writes_release_evidence" -q`

Expected: `PASS`.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md
git commit -m "ops: add release support bundle command"
```

### Task 5: Tighten Release Governance And Capacity Boundaries

**Files:**
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md`

- [ ] **Step 1: Add explicit “production-ready” definition to the release checklist**

```markdown
The current repository may be called production-ready only when all of the following are true:

1. `verify-production-readiness` passes on a fresh matrix summary.
2. API and worker services are supervised by the service manager.
3. TLS termination is configured.
4. Backup and restore drill has passed within the last 30 days.
5. Metrics scraping and minimum alerts are active.
6. Rollback owner, rollback command path, and release-support bundle location are recorded for the release.
```

- [ ] **Step 2: Add capacity-boundary guidance to the performance plan**

```markdown
## Capacity Boundary Rules

- Treat the latest green `xs/s/m` matrix as the validated envelope, not as proof of unlimited headroom.
- Any increase in module count, tenant count, or ingestion concurrency beyond the last green `m` profile requires a fresh matrix run.
- Do not claim capacity for `l` or `xl` until dedicated artifacts exist for those scales.
```

- [ ] **Step 3: Add drill cadence and ownership to the backup runbook**

```markdown
## Drill Cadence

- Run the backup/restore drill monthly.
- Record operator, date, bundle path, restored path, and integrity result.
- Escalate immediately if restore exceeds the recovery-time objective or if audit logs fail to replay.
```

- [ ] **Step 4: Verify the governance language is present**

Run: `Select-String -Path D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md,D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md,D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md -Pattern "production-ready","30 days","Capacity Boundary","monthly"`

Expected: all required governance phrases are present.

- [ ] **Step 5: Commit**

```bash
git add D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md
git commit -m "docs: tighten production governance rules"
```

## Coverage Check

- deployment and TLS closure: Task 1
- secret/config contract: Task 1
- backup and restore: Task 2
- logs, metrics, alerts, retention: Task 3
- cutover, rollback, release evidence bundle: Task 4
- operational production definition and capacity boundaries: Task 5

## Self-Review

### Spec coverage

- The plan no longer assumes performance gates are failing.
- The plan focuses on the remaining operational areas you explicitly called out: backup/restore, logging, monitoring, secrets/config, disaster drills, and release governance.

### Placeholder scan

- No `TODO`, `TBD`, or vague “add monitoring” steps remain.
- Each task includes exact paths, concrete file contents, and exact commands.

### Type consistency

- New CLI groups follow the existing Click style in `cli.py`.
- Backup and restore functions consistently use `Path` inputs and explicit empty-target validation.

## Notes For Execution

- Keep this scoped to single-node production closure. Do not reopen database, distributed queue, or multi-region architecture work in this plan.
- Reuse the existing green benchmark gate as the application baseline; only rerun performance when the validated operating envelope changes.
- Keep using `PYTEST_DEBUG_TEMPROOT` instead of a shared `--basetemp` path for deterministic local verification on this workstation.
