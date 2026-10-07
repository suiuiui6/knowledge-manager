# Production-Grade Excellent Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current benchmark-green `knowledge-manager` build into a production-grade single-node service with a real, code-backed operations contract: explicit runtime env wiring, complete backup and restore semantics, deployable service artifacts, minimum verifiable observability, and release evidence strong enough to support cutover and rollback.

**Architecture:** Keep the current file-backed single-node architecture and treat the application layer as substantially ready. Do not reopen search or retrieval tuning. Instead, add a thin operations layer around the existing CLI, HTTP server, readiness gate, and KB layout so that configuration, deployment, backup, support evidence, and recovery are all implemented and testable rather than described aspirationally in docs alone.

**Tech Stack:** Python 3.10+, Click CLI, FastAPI, Uvicorn, httpx, pytest, JSON/JSONL artifacts, systemd unit files, Caddy reverse proxy config, existing `runtime_checks`, `audit`, `ingestion_jobs`, `storage`, and `verify-production-readiness` flows.

---

## Real Current State This Plan Must Respect

The repository already has strong application-layer evidence:

- `xs`, `s`, and `m` production-gate matrix entries are green in `D:\tyh\knowledge-manager\test-results\perf-run-production-gate-20260613-r16-matrix-summary.json`
- `km verify-production-readiness` already combines readiness, integrity, and benchmark verdicts
- the KB root already stores operational state such as `.staging/` and `.telemetry/`, and runtime state such as `.audit/`, `.jobs/`, `.cache/`, and `.changelog/` is also designed to live under the KB tree
- source ingestion already uses environment-backed secret lookup via `api_token_env`, so the codebase has an established pattern for env-backed operational configuration

The remaining gaps are operational, not algorithmic:

- there is no first-class runtime env resolver for deployment-owned settings such as KB path, serve host/port, or log level
- `.env.production.example` does not exist and should not be invented without code that actually reads it
- backup and restore semantics are not explicit about what is captured, what is restored, and what must remain immutable
- deployment artifacts are not yet tied to executable verification commands
- support bundles and observability guidance are too thin to support real incident response

## Production Outcome For This Repo

For this repo's current architecture, "production-grade" means all of the following are true at the same time:

- deployment-owned runtime settings are read through a code-backed env contract, not only written in docs
- application-owned security toggles such as `production_mode`, `multi_tenant_mode`, and `mcp_global_resources` remain single-sourced in `config.json`, not duplicated into a second source of truth
- backup bundles explicitly include the full KB tree, a manifest describing contents and restore semantics, and optional release evidence attachments
- restore is deterministic, empty-target only, validates the bundle before copying data into place, and distinguishes between must-restore state and safe-to-rebuild derived state
- operators can run one concrete application-accessible deployment verification flow that checks service reachability, readiness, metrics, worker state, and production verdict evidence
- support bundles include enough state to debug rollout and rollback issues without guessing
- runbooks describe not just what to believe, but which concrete commands prove it

## File Structure

### Existing files to extend

- `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
  Responsibility: CLI entrypoint, serve command, worker command, release gate, operator tooling.
- `D:\tyh\knowledge-manager\src\knowledge_manager\runtime_checks.py`
  Responsibility: readiness, integrity, metrics.
- `D:\tyh\knowledge-manager\src\knowledge_manager\audit.py`
  Responsibility: audit log paths and reading.
- `D:\tyh\knowledge-manager\src\knowledge_manager\ingestion_jobs.py`
  Responsibility: job status introspection.
- `D:\tyh\knowledge-manager\src\knowledge_manager\storage.py`
  Responsibility: config loading and KB-root semantics.
- `D:\tyh\knowledge-manager\tests\test_cli.py`
- `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`
- `D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout.md`
- `D:\tyh\knowledge-manager\docs\runbooks\migration-cutover.md`
- `D:\tyh\knowledge-manager\README.md`

### New files to create

- `D:\tyh\knowledge-manager\src\knowledge_manager\runtime_env.py`
  Responsibility: code-backed runtime env parsing for deployment-owned process settings.
- `D:\tyh\knowledge-manager\scripts\backup_kb.py`
  Responsibility: create complete KB backup bundles with manifest and optional evidence attachments.
- `D:\tyh\knowledge-manager\scripts\restore_kb.py`
  Responsibility: validate and restore bundles into an empty target KB.
- `D:\tyh\knowledge-manager\tests\test_backup_restore.py`
  Responsibility: backup content completeness and restore guardrails.
- `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service`
- `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service`
- `D:\tyh\knowledge-manager\deploy\caddy\Caddyfile`
- `D:\tyh\knowledge-manager\deploy\logrotate\knowledge-manager`
- `D:\tyh\knowledge-manager\.env.production.example`
- `D:\tyh\knowledge-manager\docs\runbooks\deploy-single-node.md`
- `D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md`
- `D:\tyh\knowledge-manager\docs\runbooks\observability-and-alerting.md`

## Delivery Stages

1. `P0` Add code-backed runtime env contract and align deployment artifacts to it
2. `P0` Add complete, testable backup and restore semantics
3. `P0` Add executable deployment verification and richer support evidence
4. `P1` Tighten docs, drills, and governance around the implemented contract

### Task 1: Implement A Real Runtime Environment Contract

**Files:**
- Create: `D:\tyh\knowledge-manager\src\knowledge_manager\runtime_env.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Create: `D:\tyh\knowledge-manager\.env.production.example`
- Modify: `D:\tyh\knowledge-manager\README.md`

- [ ] **Step 1: Write the failing env-contract tests**

```python
import logging
from pathlib import Path

from knowledge_manager.runtime_env import RuntimeEnvSettings, load_runtime_env_settings


def test_runtime_env_uses_explicit_km_variables(monkeypatch, tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    monkeypatch.setenv("KM_KB_PATH", str(kb))
    monkeypatch.setenv("KM_UI_HOST", "0.0.0.0")
    monkeypatch.setenv("KM_UI_PORT", "9001")
    monkeypatch.setenv("KM_LOG_LEVEL", "INFO")

    settings = load_runtime_env_settings()

    assert settings.kb_path == kb
    assert settings.ui_host == "0.0.0.0"
    assert settings.ui_port == 9001
    assert settings.log_level == "INFO"


def test_configure_logging_uses_runtime_env_level_when_not_verbose(monkeypatch, tmp_path):
    from knowledge_manager.cli import _configure_logging

    kb = tmp_path / "kb"
    kb.mkdir()
    monkeypatch.setenv("KM_KB_PATH", str(kb))
    monkeypatch.setenv("KM_LOG_LEVEL", "INFO")

    settings = load_runtime_env_settings()
    _configure_logging(verbose=False, default_level=settings.log_level)

    assert logging.getLogger("knowledge_manager").level == logging.INFO


def test_cli_uses_runtime_env_kb_path_when_flag_is_omitted(cli_runner, tmp_path, monkeypatch):
    from knowledge_manager.cli import cli

    kb = tmp_path / "kb"
    cli_runner.invoke(cli, ["init", str(kb)])
    monkeypatch.setenv("KM_KB_PATH", str(kb))

    result = cli_runner.invoke(cli, ["stats"])

    assert result.exit_code == 0
    assert "Total modules" in result.output
```

- [ ] **Step 2: Run the focused env-contract tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "runtime_env_uses_explicit_km_variables or runtime_env_kb_path" -q`

Expected: `FAIL` because there is no `runtime_env.py` yet, `_configure_logging` has no env-backed default level, and the CLI currently defaults `--kb-path` to `Path.cwd()`.

- [ ] **Step 3: Add the runtime env module**

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeEnvSettings:
    kb_path: Path
    ui_host: str
    ui_port: int
    log_level: str


def load_runtime_env_settings() -> RuntimeEnvSettings:
    kb_path = Path(os.environ.get("KM_KB_PATH", Path.cwd()))
    ui_host = os.environ.get("KM_UI_HOST", "127.0.0.1")
    ui_port = int(os.environ.get("KM_UI_PORT", "8420"))
    log_level = os.environ.get("KM_LOG_LEVEL", "WARNING").upper()
    return RuntimeEnvSettings(
        kb_path=kb_path,
        ui_host=ui_host,
        ui_port=ui_port,
        log_level=log_level,
    )
```

- [ ] **Step 4: Wire the CLI to the runtime env contract without duplicating security config**

```python
import logging

from knowledge_manager.runtime_env import load_runtime_env_settings


def _configure_logging(verbose: bool, default_level: str = "WARNING") -> None:
    level = logging.DEBUG if verbose else getattr(logging, default_level.upper(), logging.WARNING)
    root = logging.getLogger()
    root.setLevel(level)

    package_logger = logging.getLogger("knowledge_manager")
    package_logger.setLevel(level)
    package_logger.propagate = True

    if verbose and not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        root.addHandler(handler)


@click.group()
@click.version_option("0.5.2", prog_name="km")
@click.option(
    "--kb-path",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to the knowledge base directory",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose logging output",
)
@click.pass_context
def cli(ctx: click.Context, kb_path: Path | None, verbose: bool) -> None:
    """Knowledge Manager — lightweight AI knowledge management."""
    ctx.ensure_object(dict)
    runtime_settings = load_runtime_env_settings()
    resolved_kb = Path(kb_path) if kb_path is not None else runtime_settings.kb_path
    ctx.obj["kb_path"] = resolved_kb
    ctx.obj["verbose"] = verbose
    ctx.obj["runtime_env"] = runtime_settings

    _configure_logging(verbose, runtime_settings.log_level)
    if verbose:
        logger.debug("Verbose logging enabled")
```

```python
@cli.command()
@click.option("--ui", is_flag=True, help="Start MCP + Web UI (FastAPI on localhost:8420)")
@click.option("--host", default=None, help="Host to bind the Web UI server")
@click.option("--port", default=None, type=int, help="Port for the Web UI server")
@click.pass_context
def serve(ctx: click.Context, ui: bool, host: str | None, port: int | None) -> None:
    """Run the MCP server over stdio. Use --ui for MCP + Web UI mode."""
    kb = ctx.obj["kb_path"]
    runtime_env = ctx.obj["runtime_env"]
    resolved_host = host or runtime_env.ui_host
    resolved_port = port or runtime_env.ui_port
    ...
    console.print(f"  Web UI: http://{resolved_host}:{resolved_port}")
    uvicorn.run(app, host=resolved_host, port=resolved_port, log_level=runtime_env.log_level.lower())
```

- [ ] **Step 5: Create the env example and README contract from the implemented wiring only**

```dotenv
KM_KB_PATH=/opt/knowledge-manager/kb
KM_UI_HOST=127.0.0.1
KM_UI_PORT=8420
KM_LOG_LEVEL=INFO

# Security and tenancy remain single-sourced in kb/config.json:
# - security.production_mode
# - security.multi_tenant_mode
# - security.mcp_global_resources
```

```markdown
## Runtime Environment Contract

Deployment-owned process settings are read from environment variables:

- `KM_KB_PATH`
- `KM_UI_HOST`
- `KM_UI_PORT`
- `KM_LOG_LEVEL`

Security mode, tenancy, and MCP exposure remain application config and stay in `kb/config.json`.

## Migration Note

Before this change, commands without `--kb-path` always defaulted to the current working directory.
After this change, commands without `--kb-path` resolve the KB path from `KM_KB_PATH` first and fall back to the current working directory only when `KM_KB_PATH` is unset.
Any existing shell profile, service unit, or automation that exports `KM_KB_PATH` will therefore change the default KB target for bare `km ...` commands.
```

- [ ] **Step 6: Re-run the env-contract tests**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "runtime_env_uses_explicit_km_variables or runtime_env_kb_path" -q`

Expected: `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\runtime_env.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\.env.production.example D:\tyh\knowledge-manager\README.md
git commit -m "ops: add runtime env contract"
```

### Task 2: Make Backup And Restore Semantics Explicit And Complete

**Files:**
- Create: `D:\tyh\knowledge-manager\scripts\backup_kb.py`
- Create: `D:\tyh\knowledge-manager\scripts\restore_kb.py`
- Create: `D:\tyh\knowledge-manager\tests\test_backup_restore.py`
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md`

- [ ] **Step 1: Write the failing backup completeness tests**

```python
import json

from knowledge_manager.schemas import Index
from knowledge_manager.storage import save_index


def test_backup_bundle_includes_hidden_operational_dirs_and_manifest(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="backup"), kb)
    (kb / ".audit").mkdir()
    (kb / ".audit" / "audit.jsonl").write_text('{"ok":true}\n', encoding="utf-8")
    (kb / ".jobs").mkdir()
    (kb / ".jobs" / "state.json").write_text("{}", encoding="utf-8")
    (kb / ".cache").mkdir()
    (kb / ".cache" / "state.json").write_text("{}", encoding="utf-8")
    (kb / ".changelog").mkdir()
    (kb / ".changelog" / "2026-06-13.json").write_text("[]", encoding="utf-8")

    from scripts.backup_kb import create_backup_bundle, inspect_backup_bundle

    bundle = create_backup_bundle(kb, tmp_path / "backups")
    summary = inspect_backup_bundle(bundle)

    assert "kb/.audit/audit.jsonl" in summary["files"]
    assert "kb/.jobs/state.json" in summary["files"]
    assert "kb/.cache/state.json" in summary["files"]
    assert "kb/.changelog/2026-06-13.json" in summary["files"]
    assert summary["manifest"]["restore_policy"] == "empty-target-only"


def test_restore_bundle_refuses_nonempty_target(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    save_index(Index(description="restore"), kb)

    from scripts.backup_kb import create_backup_bundle
    from scripts.restore_kb import restore_backup_bundle

    bundle = create_backup_bundle(kb, tmp_path / "backups")
    target = tmp_path / "target"
    target.mkdir()
    (target / "keep.txt").write_text("busy", encoding="utf-8")

    import pytest
    with pytest.raises(ValueError, match="empty"):
        restore_backup_bundle(bundle, target)


def test_cli_backup_create_emits_bundle_path(cli_runner, initialized_kb, tmp_path):
    from knowledge_manager.cli import cli

    output_dir = tmp_path / "backups"
    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "backup",
            "create",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip().endswith(".zip")
```

- [ ] **Step 2: Run the backup tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src;D:\tyh\knowledge-manager'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_backup_restore.py -q`

Expected: `FAIL` because the scripts and CLI wrappers do not exist yet.

- [ ] **Step 3: Implement bundle creation with full-KB semantics**

```python
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def create_backup_bundle(kb_path: Path, output_dir: Path, attachments: list[Path] | None = None) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / f"knowledge-manager-backup-{timestamp}"
    shutil.copytree(kb_path, staging / "kb")

    attached_files: list[str] = []
    for attachment in attachments or []:
        target = staging / "attachments" / attachment.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(attachment, target)
        attached_files.append(f"attachments/{attachment.name}")

    manifest = {
        "created_at": timestamp,
        "app_version": "0.5.2",
        "source_kb_path": str(kb_path),
        "contents": {
            "kb_tree": "full recursive copy, including hidden operational directories under the KB root",
            "attachments": attached_files,
        },
        "restore_policy": "empty-target-only",
        "restore_includes": [
            "all visible KB content",
            "must-restore operational state such as .audit/, .jobs/, config, and release evidence attachments",
            "safe-to-rebuild derived state such as .cache/ when present",
            "manifest metadata required to validate restore semantics",
        ],
        "restore_tiers": {
            "must_restore": [
                "module content and index state",
                "config.json and auth or RBAC material stored under the KB root",
                ".audit/",
                ".jobs/",
                ".staging/",
                ".telemetry/",
                ".changelog/",
            ],
            "rebuildable_after_restore": [
                ".cache/",
                "derived search or recommendation artifacts that can be regenerated from the restored KB state",
            ],
        },
        "non_restored_items": [
            "systemd units are infra artifacts and are not copied into the restored KB",
            "reverse proxy config is infra-managed and is not copied into the restored KB",
        ],
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    archive_base = output_dir / f"knowledge-manager-backup-{timestamp}"
    archive_path = shutil.make_archive(str(archive_base), "zip", root_dir=staging.parent, base_dir=staging.name)
    shutil.rmtree(staging)
    return Path(archive_path)


def inspect_backup_bundle(bundle_path: Path) -> dict:
    with zipfile.ZipFile(bundle_path) as zf:
        names = sorted(zf.namelist())
        manifest_name = next(name for name in names if name.endswith("manifest.json"))
        manifest = json.loads(zf.read(manifest_name).decode("utf-8"))
    return {"files": names, "manifest": manifest}
```

- [ ] **Step 4: Implement restore with validation**

```python
from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path


def restore_backup_bundle(bundle_path: Path, target_kb_path: Path) -> None:
    if target_kb_path.exists() and any(target_kb_path.iterdir()):
        raise ValueError(f"restore target must be empty: {target_kb_path}")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir)
        shutil.unpack_archive(str(bundle_path), str(tmp_root))
        extracted_root = next(tmp_root.iterdir())
        manifest = json.loads((extracted_root / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("restore_policy") != "empty-target-only":
            raise ValueError("unsupported restore policy")
        source_kb = extracted_root / "kb"
        if not (source_kb / "index.json").exists():
            raise ValueError("backup bundle missing kb/index.json")
        shutil.copytree(source_kb, target_kb_path, dirs_exist_ok=True)
```

- [ ] **Step 5: Add CLI wrappers and the drill runbook**

```python
@cli.group("backup")
def backup() -> None:
    """Backup and restore a knowledge base."""


@backup.command("create")
@click.option("--output-dir", type=click.Path(path_type=Path), required=True)
@click.option("--attach", "attachments", type=click.Path(path_type=Path, exists=True), multiple=True)
@click.pass_context
def backup_create(ctx: click.Context, output_dir: Path, attachments: tuple[Path, ...]) -> None:
    from scripts.backup_kb import create_backup_bundle
    bundle = create_backup_bundle(ctx.obj["kb_path"], output_dir, attachments=list(attachments))
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
# Backup Restore Drill

## Scope

Every backup bundle must contain the full KB tree, including hidden runtime state under the KB root such as `.audit/`, `.jobs/`, `.cache/`, `.staging/`, `.telemetry/`, and `.changelog/` when present.

## Restore Tiers

- Must restore exactly: module content, index state, `config.json`, auth or RBAC material stored under the KB root, `.audit/`, `.jobs/`, `.staging/`, `.telemetry/`, and `.changelog/`.
- Restore if present but safe to rebuild: `.cache/` and other purely derived runtime artifacts.
- Do not restore from the bundle: systemd units, reverse proxy config, and other infra-managed host artifacts.

## Restore Semantics

- Restore into an empty target only.
- Do not merge with an existing KB.
- Reinstall infra-managed artifacts such as systemd units and reverse proxy config from source control, not from the KB backup.
- After restoring rebuildable artifacts such as `.cache/`, operators may either keep them as restored or regenerate them through the normal repair and rebuild flows.

## Drill Procedure

1. `km --kb-path <kb> backup create --output-dir <dir> --attach <fresh-matrix-summary.json>`
2. `km backup restore --bundle <bundle.zip> --target-kb <empty-target>`
3. `km --kb-path <empty-target> integrity --format json`
4. `km --kb-path <empty-target> verify-production-readiness --matrix-summary <fresh-matrix-summary.json>`
```

- [ ] **Step 6: Re-run backup tests**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src;D:\tyh\knowledge-manager'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_backup_restore.py D:\tyh\knowledge-manager\tests\test_cli.py -k "backup or restore" -q`

Expected: `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\scripts\backup_kb.py D:\tyh\knowledge-manager\scripts\restore_kb.py D:\tyh\knowledge-manager\tests\test_backup_restore.py D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md D:\tyh\knowledge-manager\tests\test_cli.py
git commit -m "ops: add complete backup restore semantics"
```

### Task 3: Add Application-Accessible Deployment Verification And Support Bundles

**Files:**
- Modify: `D:\tyh\knowledge-manager\src\knowledge_manager\cli.py`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Create: `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service`
- Create: `D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service`
- Create: `D:\tyh\knowledge-manager\deploy\caddy\Caddyfile`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\deploy-single-node.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`

- [ ] **Step 1: Write the failing deployment verification tests**

```python
def test_support_bundle_includes_version_config_jobs_and_log_paths(cli_runner, initialized_kb, tmp_path):
    from knowledge_manager.cli import cli

    matrix_summary = tmp_path / "matrix-summary.json"
    matrix_summary.write_text(
        '{"xs":{"release_verdict":{"ready_for_production":true}},"s":{"release_verdict":{"ready_for_production":true}},"m":{"release_verdict":{"ready_for_production":true}}}',
        encoding="utf-8",
    )
    output_dir = tmp_path / "bundle"

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads((output_dir / "release-support-bundle.json").read_text(encoding="utf-8"))
    assert payload["app_version"] == "0.5.2"
    assert "config_summary" in payload
    assert "job_summary" in payload
    assert "log_locations" in payload
    assert "recent_jobs" in payload
    assert "release_evidence" in payload


def test_verify_deployment_reports_ready_metrics_and_worker_state(cli_runner, initialized_kb, tmp_path, monkeypatch):
    from knowledge_manager.cli import cli

    matrix_summary = tmp_path / "matrix-summary.json"
    matrix_summary.write_text(
        '{"xs":{"release_verdict":{"ready_for_production":true}},"s":{"release_verdict":{"ready_for_production":true}},"m":{"release_verdict":{"ready_for_production":true}}}',
        encoding="utf-8",
    )

    class FakeResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text
        def json(self):
            return {"ready": True}

    def fake_get(url, timeout=5.0):
        if url.endswith("/api/ready"):
            return FakeResponse(200, '{"ready": true}')
        if url.endswith("/api/metrics"):
            return FakeResponse(200, "knowledge_manager_modules_total 1\n")
        raise AssertionError(url)

    monkeypatch.setattr("knowledge_manager.cli.httpx.get", fake_get)

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "verify-deployment",
            "--base-url",
            "http://127.0.0.1:8420",
            "--matrix-summary",
            str(matrix_summary),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["http"]["ready_status"] == 200
    assert payload["http"]["metrics_status"] == 200
    assert "worker" in payload
```

- [ ] **Step 2: Run the focused deployment tests and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "support_bundle_includes_version or verify_deployment_reports_ready" -q`

Expected: `FAIL`.

- [ ] **Step 3: Implement richer support bundles**

```python
@cli.group("support")
def support() -> None:
    """Generate operator support artifacts."""


@support.command("bundle")
@click.option("--output-dir", type=click.Path(path_type=Path), required=True)
@click.option("--matrix-summary", type=click.Path(path_type=Path, exists=True), required=True)
@click.pass_context
def support_bundle(ctx: click.Context, output_dir: Path, matrix_summary: Path) -> None:
    from knowledge_manager.ingestion_jobs import list_ingestion_jobs
    from knowledge_manager.performance_benchmarks import build_production_readiness_verdict
    from knowledge_manager.runtime_checks import evaluate_readiness, run_integrity_check
    from knowledge_manager.storage import sanitize_config

    kb = ctx.obj["kb_path"]
    output_dir.mkdir(parents=True, exist_ok=True)
    cfg = _load_config(kb)
    jobs = list_ingestion_jobs(kb)
    recent_jobs = [job.model_dump(mode="json") for job in jobs[:10]]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app_version": "0.5.2",
        "kb_path": str(kb),
        "config_summary": sanitize_config(cfg).model_dump(mode="json"),
        "readiness": evaluate_readiness(kb),
        "integrity": run_integrity_check(kb),
        "production_verdict": build_production_readiness_verdict(kb, matrix_summary),
        "release_evidence": {
            "matrix_summary_path": str(matrix_summary),
            "matrix_summary_mtime": datetime.fromtimestamp(matrix_summary.stat().st_mtime, tz=timezone.utc).isoformat(),
        },
        "job_summary": {
            "total": len(jobs),
            "failed": sum(1 for job in jobs if job.status == "failed"),
            "running": sum(1 for job in jobs if job.status == "running"),
            "queued": sum(1 for job in jobs if job.status == "queued"),
        },
        "recent_jobs": recent_jobs,
        "log_locations": {
            "audit": str(kb / ".audit" / "audit.jsonl"),
            "telemetry": str(kb / ".telemetry"),
            "jobs": str(kb / ".jobs"),
            "service_logs": "/var/log/knowledge-manager/*.log or journald",
        },
    }
    path = output_dir / "release-support-bundle.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(str(path))
```

- [ ] **Step 4: Implement deployment verification**

```python
@cli.command("verify-deployment")
@click.option("--base-url", required=True)
@click.option("--matrix-summary", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
@click.pass_context
def verify_deployment(ctx: click.Context, base_url: str, matrix_summary: Path, fmt: str) -> None:
    from knowledge_manager.ingestion_jobs import list_ingestion_jobs
    from knowledge_manager.performance_benchmarks import build_production_readiness_verdict

    kb = ctx.obj["kb_path"]
    ready = httpx.get(f"{base_url}/api/ready", timeout=5.0)
    metrics = httpx.get(f"{base_url}/api/metrics", timeout=5.0)
    jobs = list_ingestion_jobs(kb)
    ready_ok = ready.status_code == 200
    metrics_nonempty = bool(metrics.text.strip())
    metrics_ok = metrics.status_code == 200 and metrics_nonempty
    failed_jobs = sum(1 for job in jobs if job.status == "failed")
    stale_running_jobs = sum(
        1 for job in jobs
        if job.status == "running" and job.lease_expires_at is not None and job.lease_expires_at < datetime.now(timezone.utc)
    )
    production_verdict = build_production_readiness_verdict(kb, matrix_summary)
    payload = {
        "ok": ready_ok and metrics_ok and failed_jobs == 0 and stale_running_jobs == 0 and production_verdict["ready_for_production"],
        "http": {
            "ready_status": ready.status_code,
            "metrics_status": metrics.status_code,
            "metrics_nonempty": metrics_nonempty,
        },
        "worker": {
            "failed_jobs": failed_jobs,
            "stale_running_jobs": stale_running_jobs,
        },
        "production_verdict": production_verdict,
    }
    if fmt == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        raise click.exceptions.Exit(0 if payload["ok"] else 1)
    click.echo(f"ready={payload['http']['ready_status']} metrics={payload['http']['metrics_status']}")
    raise click.exceptions.Exit(0 if payload["ok"] else 1)
```

- [ ] **Step 5: Add deploy artifacts aligned to the implemented env contract**

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
ExecStartPre=/usr/bin/install -d -o km -g km /var/log/knowledge-manager
ExecStartPre=/usr/bin/test -f /opt/knowledge-manager/kb/index.json
ExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

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
ExecStartPre=/usr/bin/install -d -o km -g km /var/log/knowledge-manager
ExecStartPre=/usr/bin/test -f /opt/knowledge-manager/kb/index.json
ExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

```caddy
km.example.com {
    encode gzip zstd
    reverse_proxy 127.0.0.1:8420
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "DENY"
        Referrer-Policy "no-referrer"
    }
}
```

- [ ] **Step 6: Add a concrete single-node deployment runbook**

````markdown
# Single-Node Deployment

## Install

```bash
install -d -o km -g km /opt/knowledge-manager /opt/knowledge-manager/kb /opt/knowledge-manager/release-artifacts /var/log/knowledge-manager
cp deploy/systemd/knowledge-manager-api.service /etc/systemd/system/
cp deploy/systemd/knowledge-manager-worker.service /etc/systemd/system/
cp deploy/caddy/Caddyfile /etc/caddy/Caddyfile
cp .env.production.example /opt/knowledge-manager/.env.production
systemctl daemon-reload
systemctl enable --now knowledge-manager-api knowledge-manager-worker
systemctl reload caddy
```

## Verify

```bash
systemctl status knowledge-manager-api
systemctl status knowledge-manager-worker
curl -fsS http://127.0.0.1:8420/api/ready
curl -fsS http://127.0.0.1:8420/api/metrics
km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json
km --kb-path /opt/knowledge-manager/kb support bundle --output-dir /opt/knowledge-manager/release-artifacts --matrix-summary <fresh-matrix-summary.json>
```

## Infrastructure Verification

```bash
systemctl status knowledge-manager-api
systemctl status knowledge-manager-worker
systemctl cat knowledge-manager-api
systemctl cat knowledge-manager-worker
caddy validate --config /etc/caddy/Caddyfile
```

## Rollback

```bash
systemctl stop knowledge-manager-api knowledge-manager-worker
mv /opt/knowledge-manager/kb /opt/knowledge-manager/kb.rollback.$(date +%Y%m%d%H%M%S)
install -d -o km -g km /opt/knowledge-manager/kb
km backup restore --bundle <known-good-backup.zip> --target-kb /opt/knowledge-manager/kb
systemctl start knowledge-manager-api knowledge-manager-worker
km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json
```
````

- [ ] **Step 7: Document concrete verification commands**

````markdown
## Deployment Verification

```bash
systemctl status knowledge-manager-api
systemctl status knowledge-manager-worker
curl -fsS http://127.0.0.1:8420/api/ready
curl -fsS http://127.0.0.1:8420/api/metrics
km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json
km --kb-path /opt/knowledge-manager/kb support bundle --output-dir /opt/knowledge-manager/release-artifacts --matrix-summary <fresh-matrix-summary.json>
km --kb-path /opt/knowledge-manager/kb worker run --once
```
````

- [ ] **Step 8: Re-run deployment tests**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "support_bundle_includes_version or verify_deployment_reports_ready" -q`

Expected: `PASS`.

- [ ] **Step 9: Commit**

```bash
git add D:\tyh\knowledge-manager\src\knowledge_manager\cli.py D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-api.service D:\tyh\knowledge-manager\deploy\systemd\knowledge-manager-worker.service D:\tyh\knowledge-manager\deploy\caddy\Caddyfile D:\tyh\knowledge-manager\docs\runbooks\deploy-single-node.md D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md
git commit -m "ops: add deployment verification and support bundle"
```

### Task 4: Upgrade Observability From Runbook Text To A Minimum Verifiable Observability Baseline

**Files:**
- Create: `D:\tyh\knowledge-manager\deploy\logrotate\knowledge-manager`
- Create: `D:\tyh\knowledge-manager\docs\runbooks\observability-and-alerting.md`
- Modify: `D:\tyh\knowledge-manager\tests\test_cli.py`
- Modify: `D:\tyh\knowledge-manager\README.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`

- [ ] **Step 1: Write the failing observability assertions**

```python
from pathlib import Path


def test_observability_runbook_mentions_metrics_logs_alerts_and_bundle():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "runbooks" / "observability-and-alerting.md").read_text(encoding="utf-8")
    assert "/api/metrics" in text
    assert "audit.jsonl" in text
    assert "verify-deployment" in text
    assert "release-support-bundle.json" in text
    assert "alert" in text.lower()


def test_logrotate_policy_targets_audit_and_app_logs():
    root = Path(__file__).resolve().parents[1]
    text = (root / "deploy" / "logrotate" / "knowledge-manager").read_text(encoding="utf-8")
    assert ".audit/audit.jsonl" in text
    assert "/var/log/knowledge-manager" in text
```

- [ ] **Step 2: Run the observability assertions and verify they fail**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "observability_runbook_mentions or logrotate_policy_targets" -q`

Expected: `FAIL`.

- [ ] **Step 3: Add the logrotate policy**

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

- [ ] **Step 4: Add the observability runbook with verifiable checks**

```markdown
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

## Minimum Alerts

- readiness non-200 for 5 minutes
- metrics endpoint scrape failure for 5 minutes
- failed job count > 0
- stale running job count > 0
- disk free space below 15%
```

- [ ] **Step 5: Link the observability checks from the README and release checklist**

```markdown
Before production cutover, verify both:

- `km verify-deployment`
- `km support bundle`
```

- [ ] **Step 6: Re-run the observability assertions**

Run: `$env:PYTHONPATH='D:\tyh\knowledge-manager\src'; $env:PYTEST_DEBUG_TEMPROOT='D:\tyh\knowledge-manager\tmp\pytest'; python -m pytest D:\tyh\knowledge-manager\tests\test_cli.py -k "observability_runbook_mentions or logrotate_policy_targets" -q`

Expected: `PASS`.

- [ ] **Step 7: Commit**

```bash
git add D:\tyh\knowledge-manager\deploy\logrotate\knowledge-manager D:\tyh\knowledge-manager\docs\runbooks\observability-and-alerting.md D:\tyh\knowledge-manager\tests\test_cli.py D:\tyh\knowledge-manager\README.md D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md
git commit -m "ops: add verifiable observability contract"
```

### Task 5: Tighten Governance, Rollback, And Capacity Language Around The Implemented Tools

**Files:**
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\migration-cutover.md`
- Modify: `D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md`

- [ ] **Step 1: Add a production-grade definition tied to actual commands**

```markdown
The current repository may be called production-grade only when all of the following are true:

1. `km verify-production-readiness` passes on a fresh matrix summary.
2. `km verify-deployment` passes against the running service.
3. `km support bundle` has been generated for the release and stored with the release record.
4. The monthly backup/restore drill has passed within the last 30 days.
5. TLS termination, service supervision, and log retention config are installed from the checked-in deploy artifacts.
```

- [ ] **Step 2: Add rollback and reload command blocks**

````markdown
## Reload

```bash
systemctl daemon-reload
systemctl restart knowledge-manager-api
systemctl restart knowledge-manager-worker
km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json
```

## Rollback

```bash
systemctl stop knowledge-manager-api
systemctl stop knowledge-manager-worker
mv /opt/knowledge-manager/kb /opt/knowledge-manager/kb.rollback.$(date +%Y%m%d%H%M%S)
install -d -o km -g km /opt/knowledge-manager/kb
km backup restore --bundle <known-good-backup.zip> --target-kb /opt/knowledge-manager/kb
systemctl start knowledge-manager-api
systemctl start knowledge-manager-worker
km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json
```
````

- [ ] **Step 3: Add capacity-boundary language to the performance plan**

```markdown
## Capacity Boundary Rules

- The green `xs`, `s`, and `m` results define the currently validated operating envelope.
- Any increase beyond the last green `m` profile in module count, tenant count, or ingestion concurrency requires a fresh matrix run before release.
- Do not claim `l` or `xl` support until dedicated artifacts exist for those scales.
```

- [ ] **Step 4: Add release-record fields to rollout and migration runbooks**

```markdown
Record the following with every cutover:

- release version
- matrix summary path
- support bundle path
- backup bundle path
- operator on call
- rollback owner
```

- [ ] **Step 5: Verify governance phrases are present**

Run: `Select-String -Path D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md,D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md,D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout.md,D:\tyh\knowledge-manager\docs\runbooks\migration-cutover.md,D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md -Pattern "verify-deployment","support bundle","30 days","Capacity Boundary","rollback owner"`

Expected: all governance phrases are present.

- [ ] **Step 6: Commit**

```bash
git add D:\tyh\knowledge-manager\docs\runbooks\production-release-checklist.md D:\tyh\knowledge-manager\docs\runbooks\enterprise-performance-test-plan.md D:\tyh\knowledge-manager\docs\runbooks\enterprise-rollout.md D:\tyh\knowledge-manager\docs\runbooks\migration-cutover.md D:\tyh\knowledge-manager\docs\runbooks\backup-restore-drill.md
git commit -m "docs: tighten production governance around implemented ops tools"
```

## Coverage Check

- backup contents and restore semantics mismatch: Task 2
- env file without code-backed contract: Task 1
- deployment artifacts lacking executable checks: Task 3
- observability that is only textual: Task 4
- support bundle missing critical operational fields: Task 3
- executable deployment installation, verification, and rollback flow: Task 3
- final production-grade definition and release ownership: Task 5

## Self-Review

### Spec coverage

- The plan explicitly fixes every critique from the latest review: backup completeness, env wiring proof, deployment verification, observability verification, and richer support bundles.
- It no longer assumes application performance is the blocking problem.

### Placeholder scan

- No `TODO`, `TBD`, or deferred “later” steps remain.
- Each task contains exact files, test code, commands, and implementation snippets.

### Type consistency

- Deployment-owned settings are introduced only in `runtime_env.py`.
- Security switches remain in `config.json`, which avoids dual source of truth.
- Backup and restore both use `Path` inputs and empty-target semantics consistently.

## Notes For Execution

- Keep the scope on single-node production closure. Do not reopen distributed architecture, broker introduction, or search algorithm work in this plan.
- Prefer `PYTEST_DEBUG_TEMPROOT` over shared `--basetemp` usage on this workstation.
- When a release artifact changes the validated operating envelope, re-run the performance matrix before cutover.
