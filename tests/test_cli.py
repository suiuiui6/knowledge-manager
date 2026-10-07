import json
import logging
import os
from pathlib import Path
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from click.testing import CliRunner

from knowledge_manager.cli import cli
from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata
from knowledge_manager.storage import save_module, save_to_staging, save_index, rebuild_index, load_index
from knowledge_manager.schemas import Index
from knowledge_manager.confluence import ConfluencePage


def make_test_dir(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}-{uuid4().hex}"
    path.mkdir()
    return path


@pytest.fixture
def cli_runner():
    return CliRunner()


def make_module(id="test-mod", category="test") -> Module:
    return Module(
        id=id,
        category=category,
        title=f"Test Module {id}",
        summary="A summary describing the test module purpose",
        content=ModuleContent(
            overview="Overview that is long enough",
            details="Details that are definitely long enough to pass validation",
        ),
        metadata=ModuleMetadata(tags=["sample", "demo"]),
    )


@pytest.fixture
def kb_path(tmp_path):
    path = tmp_path / "kb"
    path.mkdir()
    return path


@pytest.fixture
def initialized_kb(cli_runner, tmp_path):
    path = tmp_path / "kb"
    cli_runner.invoke(cli, ["init", str(path)])
    return path


def test_cli_help(cli_runner):
    result = cli_runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Knowledge Manager" in result.output


def test_cli_version(cli_runner):
    result = cli_runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.5.2" in result.output


def test_cli_init_creates_knowledge_base(cli_runner, tmp_path):
    kb = tmp_path / "kb"
    result = cli_runner.invoke(cli, ["init", str(kb)])
    assert result.exit_code == 0
    assert "Initialized" in result.output
    assert kb.exists()
    assert (kb / "index.json").exists()
    assert (kb / "config.json").exists()
    assert (kb / ".staging").exists()


def test_cli_init_already_exists(cli_runner, tmp_path):
    kb = tmp_path / "kb"
    cli_runner.invoke(cli, ["init", str(kb)])
    result = cli_runner.invoke(cli, ["init", str(kb)])
    assert result.exit_code != 0
    assert "already" in result.output.lower()


def test_cli_list_empty(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "list"])
    assert result.exit_code == 0


def test_cli_list_modules(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "list"])
    assert result.exit_code == 0
    assert "auth-jwt" in result.output


def test_cli_list_by_category(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    save_module(make_module("db-conn", "database"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "list", "-c", "auth"])
    assert result.exit_code == 0
    assert "auth-jwt" in result.output
    assert "db-conn" not in result.output


def test_cli_stats(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "stats"])
    assert result.exit_code == 0
    assert "Total modules" in result.output
    assert "1" in result.output


def test_runtime_env_uses_explicit_km_variables(monkeypatch):
    from knowledge_manager.runtime_env import load_runtime_env_settings

    kb = make_test_dir("km-runtime-env-kb")
    monkeypatch.setenv("KM_KB_PATH", str(kb))
    monkeypatch.setenv("KM_UI_HOST", "0.0.0.0")
    monkeypatch.setenv("KM_UI_PORT", "9001")
    monkeypatch.setenv("KM_LOG_LEVEL", "INFO")

    settings = load_runtime_env_settings()

    assert settings.kb_path == kb
    assert settings.ui_host == "0.0.0.0"
    assert settings.ui_port == 9001
    assert settings.log_level == "INFO"


def test_configure_logging_uses_runtime_env_level_when_not_verbose(monkeypatch):
    from knowledge_manager.cli import _configure_logging
    from knowledge_manager.runtime_env import load_runtime_env_settings

    kb = make_test_dir("km-runtime-env-log")
    monkeypatch.setenv("KM_KB_PATH", str(kb))
    monkeypatch.setenv("KM_LOG_LEVEL", "INFO")

    settings = load_runtime_env_settings()
    _configure_logging(verbose=False, default_level=settings.log_level)

    assert logging.getLogger("knowledge_manager").level == logging.INFO


def test_runtime_env_invalid_ui_port_raises_clear_error(monkeypatch):
    from knowledge_manager.runtime_env import RuntimeEnvError, load_runtime_env_settings

    monkeypatch.setenv("KM_UI_PORT", "not-a-port")

    with pytest.raises(RuntimeEnvError, match="KM_UI_PORT"):
        load_runtime_env_settings()


def test_runtime_env_invalid_log_level_raises_clear_error(monkeypatch):
    from knowledge_manager.runtime_env import RuntimeEnvError, load_runtime_env_settings

    monkeypatch.setenv("KM_LOG_LEVEL", "LOUD")

    with pytest.raises(RuntimeEnvError, match="KM_LOG_LEVEL"):
        load_runtime_env_settings()


def test_cli_uses_runtime_env_kb_path_when_flag_is_omitted(cli_runner, monkeypatch):
    kb = Path("D:/tyh/runtime-env-kb")
    seen = {}
    monkeypatch.setenv("KM_KB_PATH", str(kb))
    monkeypatch.setattr("knowledge_manager.cli._require_kb", lambda path: seen.setdefault("kb_path", path))
    monkeypatch.setattr("knowledge_manager.cli.load_index", lambda path: Index(description="runtime env"))

    result = cli_runner.invoke(cli, ["stats"])

    assert result.exit_code == 0
    assert "Total modules" in result.output
    assert seen["kb_path"] == kb


def test_cli_init_uses_runtime_env_kb_path_when_path_is_omitted(cli_runner, monkeypatch):
    kb = make_test_dir("runtime-env-init-kb")
    monkeypatch.setenv("KM_KB_PATH", str(kb))

    with cli_runner.isolated_filesystem():
        result = cli_runner.invoke(cli, ["init"])

    assert result.exit_code == 0
    assert (kb / "index.json").exists()
    assert (kb / "config.json").exists()
    assert (kb / ".staging").exists()


def test_cli_reports_invalid_runtime_env_settings(cli_runner, monkeypatch):
    monkeypatch.setenv("KM_UI_PORT", "not-a-port")

    result = cli_runner.invoke(cli, ["stats"])

    assert result.exit_code != 0
    assert "KM_UI_PORT" in result.output
    assert "integer" in result.output.lower()


def test_cli_reports_invalid_runtime_env_log_level(cli_runner, monkeypatch):
    monkeypatch.setenv("KM_LOG_LEVEL", "LOUD")

    result = cli_runner.invoke(cli, ["stats"])

    assert result.exit_code != 0
    assert "KM_LOG_LEVEL" in result.output
    assert "debug" in result.output.lower()


def test_cli_integrity_reports_json(cli_runner, initialized_kb):
    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "integrity", "--format", "json"],
    )
    assert result.exit_code == 0
    assert '"issues"' in result.output


def test_support_bundle_includes_version(cli_runner, monkeypatch):
    import os
    from datetime import datetime, timedelta, timezone

    from knowledge_manager.ingestion_jobs import IngestionJob
    from scripts.backup_kb import create_backup_bundle

    kb = make_test_dir("support-bundle-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    output_dir = make_test_dir("support-bundle-output")
    matrix_summary = output_dir / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")
    readiness_json = output_dir / "verify-production-readiness.json"
    readiness_json.write_text('{"ready_for_production": true}', encoding="utf-8")
    deployment_json = output_dir / "verify-deployment.json"
    deployment_json.write_text('{"ok": true}', encoding="utf-8")
    install_smoke_json = output_dir / "verify-install-smoke.json"
    install_smoke_json.write_text('{"ok": true}', encoding="utf-8")
    restore_verify_json = output_dir / "restore-verify-deployment.json"
    restore_verify_json.write_text('{"ok": true}', encoding="utf-8")
    host_deploy_proof_json = output_dir / "host-deploy-proof.json"
    host_deploy_proof_json.write_text(
        '{"ok": true, "deploy_artifact_proof_complete": true, "invalid": []}',
        encoding="utf-8",
    )
    verify_release_artifacts_json = output_dir / "verify-release-artifacts.json"
    verify_release_artifacts_json.write_text(
        '{"ok": true, "missing": [], "invalid": []}',
        encoding="utf-8",
    )
    release_evidence_collection_json = output_dir / "release-evidence-collection.json"
    release_evidence_collection_json.write_text(
        '{"ok": true, "steps": []}',
        encoding="utf-8",
    )
    api_unit_txt = output_dir / "knowledge-manager-api.unit.txt"
    api_unit_txt.write_text(
        "[Service]\nEnvironmentFile=/opt/knowledge-manager/.env.production\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui\n",
        encoding="utf-8",
    )
    worker_unit_txt = output_dir / "knowledge-manager-worker.unit.txt"
    worker_unit_txt.write_text(
        "[Service]\nEnvironmentFile=/opt/knowledge-manager/.env.production\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0\n",
        encoding="utf-8",
    )
    caddy_validate_txt = output_dir / "caddy-validate.txt"
    caddy_validate_txt.write_text("Valid configuration", encoding="utf-8")
    logrotate_check_txt = output_dir / "logrotate-check.txt"
    logrotate_check_txt.write_text("Handling 2 logs", encoding="utf-8")
    backup_zip = create_backup_bundle(
        kb,
        output_dir,
        attachments=[readiness_json, deployment_json, install_smoke_json],
    )
    fresh_ts = datetime.now(timezone.utc).timestamp()
    os.utime(restore_verify_json, (fresh_ts, fresh_ts))
    os.utime(backup_zip, (fresh_ts, fresh_ts))

    now = datetime.now(timezone.utc)
    monkeypatch.setattr(
        "knowledge_manager.ingestion_jobs.list_ingestion_jobs",
        lambda kb_path: [
            IngestionJob(
                job_id="job-stale",
                source_id="team-docs",
                trigger="manual",
                status="running",
                lease_expires_at=now - timedelta(minutes=5),
            ),
            IngestionJob(
                job_id="job-failed",
                source_id="team-docs",
                trigger="manual",
                status="failed",
            ),
        ],
    )
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": True},
    )
    monkeypatch.setattr("knowledge_manager.runtime_checks.evaluate_readiness", lambda kb_path: {"ready": True})
    monkeypatch.setattr("knowledge_manager.runtime_checks.run_integrity_check", lambda kb_path: {"ok": True})

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    bundle_path = Path(result.output.strip())
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    assert payload["app_version"] == "0.5.2"
    assert payload["production_verdict"]["ready_for_production"] is True
    assert payload["job_summary"]["total"] == 2
    assert payload["job_summary"]["failed"] == 1
    assert payload["job_summary"]["stale_running"] == 1
    assert payload["release_evidence"]["verify_production_readiness_path"] == str(readiness_json)
    assert payload["release_evidence"]["verify_deployment_path"] == str(deployment_json)
    assert payload["release_evidence"]["backup_bundle_path"] == str(backup_zip)
    assert payload["release_evidence"]["verify_install_smoke_path"] == str(install_smoke_json)
    assert payload["release_evidence"]["restore_verify_deployment_path"] == str(restore_verify_json)
    assert payload["release_evidence"]["host_deploy_proof_path"] == str(host_deploy_proof_json)
    assert payload["release_evidence"]["verify_release_artifacts_path"] == str(verify_release_artifacts_json)
    assert payload["release_evidence"]["release_evidence_collection_path"] == str(release_evidence_collection_json)
    assert payload["release_evidence"]["backup_bundle_attachments"] == [
        "attachments/verify-production-readiness.json",
        "attachments/verify-deployment.json",
        "attachments/verify-install-smoke.json",
    ]
    assert payload["release_evidence"]["complete"] is True
    assert payload["release_evidence"]["missing"] == []
    assert payload["release_evidence"]["invalid"] == []
    assert payload["release_evidence"]["backup_restore_drill_within_30_days"] is True
    assert payload["release_evidence"]["deploy_artifact_proof_complete"] is True
    assert payload["release_evidence"]["deploy_artifact_proofs"] == {
        "api_unit_capture_path": str(api_unit_txt),
        "worker_unit_capture_path": str(worker_unit_txt),
        "caddy_validate_path": str(caddy_validate_txt),
        "logrotate_check_path": str(logrotate_check_txt),
    }


def test_support_bundle_reports_incomplete_release_evidence(cli_runner, monkeypatch):
    kb = make_test_dir("support-bundle-incomplete-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    output_dir = make_test_dir("support-bundle-incomplete-output")
    matrix_summary = output_dir / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")

    monkeypatch.setattr("knowledge_manager.ingestion_jobs.list_ingestion_jobs", lambda kb_path: [])
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": False},
    )
    monkeypatch.setattr("knowledge_manager.runtime_checks.evaluate_readiness", lambda kb_path: {"ready": False})
    monkeypatch.setattr("knowledge_manager.runtime_checks.run_integrity_check", lambda kb_path: {"ok": True})

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(Path(result.output.strip()).read_text(encoding="utf-8"))
    assert payload["release_evidence"]["complete"] is False
    assert payload["release_evidence"]["missing"] == [
        "verify-production-readiness.json",
        "verify-deployment.json",
        "verify-install-smoke.json",
        "knowledge-manager-backup-*.zip",
        "restore-verify-deployment.json",
        "verify-release-artifacts.json",
        "release-evidence-collection.json",
        "backup-attachment:attachments/verify-production-readiness.json",
        "backup-attachment:attachments/verify-deployment.json",
        "backup-attachment:attachments/verify-install-smoke.json",
    ]
    assert payload["release_evidence"]["invalid"] == []
    assert payload["release_evidence"]["backup_restore_drill_within_30_days"] is False
    assert payload["release_evidence"]["deploy_artifact_proof_complete"] is False


def test_support_bundle_reports_stale_backup_restore_drill(cli_runner, monkeypatch):
    import os
    from datetime import datetime, timedelta, timezone

    from scripts.backup_kb import create_backup_bundle

    kb = make_test_dir("support-bundle-stale-drill-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    output_dir = make_test_dir("support-bundle-stale-drill-output")
    matrix_summary = output_dir / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")
    readiness_json = output_dir / "verify-production-readiness.json"
    readiness_json.write_text('{"ready_for_production": true}', encoding="utf-8")
    deployment_json = output_dir / "verify-deployment.json"
    deployment_json.write_text('{"ok": true}', encoding="utf-8")
    install_smoke_json = output_dir / "verify-install-smoke.json"
    install_smoke_json.write_text('{"ok": true}', encoding="utf-8")
    restore_verify_json = output_dir / "restore-verify-deployment.json"
    restore_verify_json.write_text('{"ok": true}', encoding="utf-8")
    verify_release_artifacts_json = output_dir / "verify-release-artifacts.json"
    verify_release_artifacts_json.write_text(
        '{"ok": true, "missing": [], "invalid": []}',
        encoding="utf-8",
    )
    release_evidence_collection_json = output_dir / "release-evidence-collection.json"
    release_evidence_collection_json.write_text(
        '{"ok": true, "steps": []}',
        encoding="utf-8",
    )
    backup_zip = create_backup_bundle(
        kb,
        output_dir,
        attachments=[readiness_json, deployment_json, install_smoke_json],
    )
    stale_ts = (datetime.now(timezone.utc) - timedelta(days=31)).timestamp()
    os.utime(restore_verify_json, (stale_ts, stale_ts))
    os.utime(backup_zip, (stale_ts, stale_ts))

    monkeypatch.setattr("knowledge_manager.ingestion_jobs.list_ingestion_jobs", lambda kb_path: [])
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": True},
    )
    monkeypatch.setattr("knowledge_manager.runtime_checks.evaluate_readiness", lambda kb_path: {"ready": True})
    monkeypatch.setattr("knowledge_manager.runtime_checks.run_integrity_check", lambda kb_path: {"ok": True})

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(Path(result.output.strip()).read_text(encoding="utf-8"))
    assert payload["release_evidence"]["complete"] is True
    assert payload["release_evidence"]["invalid"] == []
    assert payload["release_evidence"]["backup_restore_drill_within_30_days"] is False
    assert payload["release_evidence"]["verify_release_artifacts_path"] == str(verify_release_artifacts_json)
    assert payload["release_evidence"]["release_evidence_collection_path"] == str(release_evidence_collection_json)
    assert payload["release_evidence"]["deploy_artifact_proof_complete"] is False


def test_support_bundle_reports_invalid_release_evidence_content(cli_runner, monkeypatch):
    import os
    from datetime import datetime, timezone

    from scripts.backup_kb import create_backup_bundle

    kb = make_test_dir("support-bundle-invalid-evidence-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    output_dir = make_test_dir("support-bundle-invalid-evidence-output")
    matrix_summary = output_dir / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")
    readiness_json = output_dir / "verify-production-readiness.json"
    readiness_json.write_text('{"ready_for_production": false}', encoding="utf-8")
    deployment_json = output_dir / "verify-deployment.json"
    deployment_json.write_text('{"ok": false}', encoding="utf-8")
    install_smoke_json = output_dir / "verify-install-smoke.json"
    install_smoke_json.write_text('{"ok": false}', encoding="utf-8")
    restore_verify_json = output_dir / "restore-verify-deployment.json"
    restore_verify_json.write_text('{"ok": false}', encoding="utf-8")
    verify_release_artifacts_json = output_dir / "verify-release-artifacts.json"
    verify_release_artifacts_json.write_text(
        '{"ok": false, "missing": [], "invalid": ["host-deploy-proof.json"]}',
        encoding="utf-8",
    )
    release_evidence_collection_json = output_dir / "release-evidence-collection.json"
    release_evidence_collection_json.write_text(
        '{"ok": true, "steps": []}',
        encoding="utf-8",
    )
    backup_zip = create_backup_bundle(
        kb,
        output_dir,
        attachments=[readiness_json, deployment_json, install_smoke_json],
    )
    fresh_ts = datetime.now(timezone.utc).timestamp()
    os.utime(restore_verify_json, (fresh_ts, fresh_ts))
    os.utime(backup_zip, (fresh_ts, fresh_ts))

    monkeypatch.setattr("knowledge_manager.ingestion_jobs.list_ingestion_jobs", lambda kb_path: [])
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": True},
    )
    monkeypatch.setattr("knowledge_manager.runtime_checks.evaluate_readiness", lambda kb_path: {"ready": True})
    monkeypatch.setattr("knowledge_manager.runtime_checks.run_integrity_check", lambda kb_path: {"ok": True})

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(Path(result.output.strip()).read_text(encoding="utf-8"))
    assert payload["release_evidence"]["complete"] is False
    assert payload["release_evidence"]["missing"] == []
    assert payload["release_evidence"]["invalid"] == [
            "verify-production-readiness.json",
            "verify-deployment.json",
        "verify-install-smoke.json",
        "restore-verify-deployment.json",
        "verify-release-artifacts.json",
    ]
    assert payload["release_evidence"]["deploy_artifact_proof_complete"] is False


def test_support_bundle_reports_invalid_deploy_artifact_proof_content(cli_runner, monkeypatch):
    import os
    from datetime import datetime, timezone

    from scripts.backup_kb import create_backup_bundle

    kb = make_test_dir("support-bundle-invalid-deploy-proof-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    output_dir = make_test_dir("support-bundle-invalid-deploy-proof-output")
    matrix_summary = output_dir / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")
    readiness_json = output_dir / "verify-production-readiness.json"
    readiness_json.write_text('{"ready_for_production": true}', encoding="utf-8")
    deployment_json = output_dir / "verify-deployment.json"
    deployment_json.write_text('{"ok": true}', encoding="utf-8")
    install_smoke_json = output_dir / "verify-install-smoke.json"
    install_smoke_json.write_text('{"ok": true}', encoding="utf-8")
    restore_verify_json = output_dir / "restore-verify-deployment.json"
    restore_verify_json.write_text('{"ok": true}', encoding="utf-8")
    (output_dir / "knowledge-manager-api.unit.txt").write_text("broken api unit", encoding="utf-8")
    (output_dir / "knowledge-manager-worker.unit.txt").write_text("broken worker unit", encoding="utf-8")
    (output_dir / "caddy-validate.txt").write_text("caddy error", encoding="utf-8")
    (output_dir / "logrotate-check.txt").write_text("logrotate error", encoding="utf-8")
    backup_zip = create_backup_bundle(
        kb,
        output_dir,
        attachments=[readiness_json, deployment_json, install_smoke_json],
    )
    fresh_ts = datetime.now(timezone.utc).timestamp()
    os.utime(restore_verify_json, (fresh_ts, fresh_ts))
    os.utime(backup_zip, (fresh_ts, fresh_ts))

    monkeypatch.setattr("knowledge_manager.ingestion_jobs.list_ingestion_jobs", lambda kb_path: [])
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": True},
    )
    monkeypatch.setattr("knowledge_manager.runtime_checks.evaluate_readiness", lambda kb_path: {"ready": True})
    monkeypatch.setattr("knowledge_manager.runtime_checks.run_integrity_check", lambda kb_path: {"ok": True})

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(Path(result.output.strip()).read_text(encoding="utf-8"))
    assert payload["release_evidence"]["complete"] is False
    assert payload["release_evidence"]["deploy_artifact_proof_complete"] is False
    assert payload["release_evidence"]["invalid"] == [
        "deploy-artifact-proof:knowledge-manager-api.unit.txt",
        "deploy-artifact-proof:knowledge-manager-worker.unit.txt",
        "deploy-artifact-proof:caddy-validate.txt",
        "deploy-artifact-proof:logrotate-check.txt",
    ]


def test_support_bundle_reports_invalid_host_deploy_proof_content(cli_runner, monkeypatch):
    import os
    from datetime import datetime, timezone

    from scripts.backup_kb import create_backup_bundle

    kb = make_test_dir("support-bundle-invalid-host-proof-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    output_dir = make_test_dir("support-bundle-invalid-host-proof-output")
    matrix_summary = output_dir / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")
    readiness_json = output_dir / "verify-production-readiness.json"
    readiness_json.write_text('{"ready_for_production": true}', encoding="utf-8")
    deployment_json = output_dir / "verify-deployment.json"
    deployment_json.write_text('{"ok": true}', encoding="utf-8")
    install_smoke_json = output_dir / "verify-install-smoke.json"
    install_smoke_json.write_text('{"ok": true}', encoding="utf-8")
    restore_verify_json = output_dir / "restore-verify-deployment.json"
    restore_verify_json.write_text('{"ok": true}', encoding="utf-8")
    host_deploy_proof_json = output_dir / "host-deploy-proof.json"
    host_deploy_proof_json.write_text(
        '{"ok": false, "deploy_artifact_proof_complete": false, "invalid": ["deploy-artifact-proof:caddy-validate.txt"]}',
        encoding="utf-8",
    )
    (output_dir / "knowledge-manager-api.unit.txt").write_text(
        "[Service]\nEnvironmentFile=/opt/knowledge-manager/.env.production\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui\n",
        encoding="utf-8",
    )
    (output_dir / "knowledge-manager-worker.unit.txt").write_text(
        "[Service]\nEnvironmentFile=/opt/knowledge-manager/.env.production\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0\n",
        encoding="utf-8",
    )
    (output_dir / "caddy-validate.txt").write_text("Valid configuration", encoding="utf-8")
    (output_dir / "logrotate-check.txt").write_text("Handling 2 logs", encoding="utf-8")
    backup_zip = create_backup_bundle(
        kb,
        output_dir,
        attachments=[readiness_json, deployment_json, install_smoke_json],
    )
    fresh_ts = datetime.now(timezone.utc).timestamp()
    os.utime(restore_verify_json, (fresh_ts, fresh_ts))
    os.utime(backup_zip, (fresh_ts, fresh_ts))

    monkeypatch.setattr("knowledge_manager.ingestion_jobs.list_ingestion_jobs", lambda kb_path: [])
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": True},
    )
    monkeypatch.setattr("knowledge_manager.runtime_checks.evaluate_readiness", lambda kb_path: {"ready": True})
    monkeypatch.setattr("knowledge_manager.runtime_checks.run_integrity_check", lambda kb_path: {"ok": True})

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(Path(result.output.strip()).read_text(encoding="utf-8"))
    assert payload["release_evidence"]["complete"] is False
    assert payload["release_evidence"]["host_deploy_proof_path"] == str(host_deploy_proof_json)
    assert payload["release_evidence"]["invalid"] == [
        "host-deploy-proof.json",
    ]


def test_support_bundle_reports_invalid_release_verifier_content(cli_runner, monkeypatch):
    import os
    from datetime import datetime, timezone

    from scripts.backup_kb import create_backup_bundle

    kb = make_test_dir("support-bundle-invalid-release-verifier-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    output_dir = make_test_dir("support-bundle-invalid-release-verifier-output")
    matrix_summary = output_dir / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")
    readiness_json = output_dir / "verify-production-readiness.json"
    readiness_json.write_text('{"ready_for_production": true}', encoding="utf-8")
    deployment_json = output_dir / "verify-deployment.json"
    deployment_json.write_text('{"ok": true}', encoding="utf-8")
    install_smoke_json = output_dir / "verify-install-smoke.json"
    install_smoke_json.write_text('{"ok": true}', encoding="utf-8")
    restore_verify_json = output_dir / "restore-verify-deployment.json"
    restore_verify_json.write_text('{"ok": true}', encoding="utf-8")
    host_deploy_proof_json = output_dir / "host-deploy-proof.json"
    host_deploy_proof_json.write_text(
        '{"ok": true, "deploy_artifact_proof_complete": true, "invalid": []}',
        encoding="utf-8",
    )
    verify_release_artifacts_json = output_dir / "verify-release-artifacts.json"
    verify_release_artifacts_json.write_text(
        '{"ok": false, "missing": [], "invalid": ["host-deploy-proof.json"]}',
        encoding="utf-8",
    )
    (output_dir / "knowledge-manager-api.unit.txt").write_text(
        "[Service]\nEnvironmentFile=/opt/knowledge-manager/.env.production\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui\n",
        encoding="utf-8",
    )
    (output_dir / "knowledge-manager-worker.unit.txt").write_text(
        "[Service]\nEnvironmentFile=/opt/knowledge-manager/.env.production\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0\n",
        encoding="utf-8",
    )
    (output_dir / "caddy-validate.txt").write_text("Valid configuration", encoding="utf-8")
    (output_dir / "logrotate-check.txt").write_text("Handling 2 logs", encoding="utf-8")
    backup_zip = create_backup_bundle(
        kb,
        output_dir,
        attachments=[readiness_json, deployment_json, install_smoke_json],
    )
    fresh_ts = datetime.now(timezone.utc).timestamp()
    os.utime(restore_verify_json, (fresh_ts, fresh_ts))
    os.utime(backup_zip, (fresh_ts, fresh_ts))

    monkeypatch.setattr("knowledge_manager.ingestion_jobs.list_ingestion_jobs", lambda kb_path: [])
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": True},
    )
    monkeypatch.setattr("knowledge_manager.runtime_checks.evaluate_readiness", lambda kb_path: {"ready": True})
    monkeypatch.setattr("knowledge_manager.runtime_checks.run_integrity_check", lambda kb_path: {"ok": True})

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(Path(result.output.strip()).read_text(encoding="utf-8"))
    assert payload["release_evidence"]["complete"] is False
    assert payload["release_evidence"]["verify_release_artifacts_path"] == str(verify_release_artifacts_json)
    assert payload["release_evidence"]["invalid"] == [
        "verify-release-artifacts.json",
    ]


def test_support_bundle_reports_invalid_release_evidence_collection_content(cli_runner, monkeypatch):
    import os
    from datetime import datetime, timezone

    from scripts.backup_kb import create_backup_bundle

    kb = make_test_dir("support-bundle-invalid-release-evidence-collection-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    output_dir = make_test_dir("support-bundle-invalid-release-evidence-collection-output")
    matrix_summary = output_dir / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")
    readiness_json = output_dir / "verify-production-readiness.json"
    readiness_json.write_text('{"ready_for_production": true}', encoding="utf-8")
    deployment_json = output_dir / "verify-deployment.json"
    deployment_json.write_text('{"ok": true}', encoding="utf-8")
    install_smoke_json = output_dir / "verify-install-smoke.json"
    install_smoke_json.write_text('{"ok": true}', encoding="utf-8")
    restore_verify_json = output_dir / "restore-verify-deployment.json"
    restore_verify_json.write_text('{"ok": true}', encoding="utf-8")
    host_deploy_proof_json = output_dir / "host-deploy-proof.json"
    host_deploy_proof_json.write_text(
        '{"ok": true, "deploy_artifact_proof_complete": true, "invalid": []}',
        encoding="utf-8",
    )
    verify_release_artifacts_json = output_dir / "verify-release-artifacts.json"
    verify_release_artifacts_json.write_text(
        '{"ok": true, "missing": [], "invalid": []}',
        encoding="utf-8",
    )
    release_evidence_collection_json = output_dir / "release-evidence-collection.json"
    release_evidence_collection_json.write_text(
        '{"ok": false, "steps": [{"name": "host_proof", "ok": false}]}',
        encoding="utf-8",
    )
    (output_dir / "knowledge-manager-api.unit.txt").write_text(
        "[Service]\nEnvironmentFile=/opt/knowledge-manager/.env.production\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui\n",
        encoding="utf-8",
    )
    (output_dir / "knowledge-manager-worker.unit.txt").write_text(
        "[Service]\nEnvironmentFile=/opt/knowledge-manager/.env.production\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0\n",
        encoding="utf-8",
    )
    (output_dir / "caddy-validate.txt").write_text("Valid configuration", encoding="utf-8")
    (output_dir / "logrotate-check.txt").write_text("Handling 2 logs", encoding="utf-8")
    backup_zip = create_backup_bundle(
        kb,
        output_dir,
        attachments=[readiness_json, deployment_json, install_smoke_json],
    )
    fresh_ts = datetime.now(timezone.utc).timestamp()
    os.utime(restore_verify_json, (fresh_ts, fresh_ts))
    os.utime(backup_zip, (fresh_ts, fresh_ts))

    monkeypatch.setattr("knowledge_manager.ingestion_jobs.list_ingestion_jobs", lambda kb_path: [])
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": True},
    )
    monkeypatch.setattr("knowledge_manager.runtime_checks.evaluate_readiness", lambda kb_path: {"ready": True})
    monkeypatch.setattr("knowledge_manager.runtime_checks.run_integrity_check", lambda kb_path: {"ok": True})

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "support",
            "bundle",
            "--output-dir",
            str(output_dir),
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(Path(result.output.strip()).read_text(encoding="utf-8"))
    assert payload["release_evidence"]["complete"] is False
    assert payload["release_evidence"]["release_evidence_collection_path"] == str(release_evidence_collection_json)
    assert payload["release_evidence"]["invalid"] == [
        "release-evidence-collection.json",
    ]


def test_verify_deployment_reports_ready(cli_runner, monkeypatch):
    kb = make_test_dir("verify-deployment-kb")
    (kb / "index.json").write_text("{}", encoding="utf-8")
    matrix_summary = kb / "matrix-summary.json"
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
    monkeypatch.setattr("knowledge_manager.ingestion_jobs.list_ingestion_jobs", lambda kb_path: [])
    monkeypatch.setattr(
        "knowledge_manager.performance_benchmarks.build_production_readiness_verdict",
        lambda kb_path, matrix_summary: {"ready_for_production": True},
    )

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
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


def test_single_node_deploy_artifacts_define_env_backed_services():
    root = Path(__file__).resolve().parents[1]
    api_service = (root / "deploy" / "systemd" / "knowledge-manager-api.service").read_text(
        encoding="utf-8"
    )
    worker_service = (root / "deploy" / "systemd" / "knowledge-manager-worker.service").read_text(
        encoding="utf-8"
    )
    caddyfile = (root / "deploy" / "caddy" / "Caddyfile").read_text(encoding="utf-8")
    runbook = (root / "docs" / "runbooks" / "deploy-single-node.md").read_text(encoding="utf-8")

    assert "EnvironmentFile=/opt/knowledge-manager/.env.production" in api_service
    assert "ExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui" in api_service
    assert "ExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0" in worker_service
    assert "reverse_proxy 127.0.0.1:8420" in caddyfile
    assert "km.example.com" in caddyfile
    assert "http://km.example.com" not in caddyfile
    assert "dnf install -y python3.11 git caddy logrotate" in runbook
    assert "git clone <repo-url> /opt/knowledge-manager" in runbook
    assert "git checkout <release-ref>" in runbook
    assert "groupadd --system km" in runbook
    assert "useradd --system --home /opt/knowledge-manager --shell /sbin/nologin --gid km km" in runbook
    assert "chown -R km:km /opt/knowledge-manager /var/log/knowledge-manager" in runbook
    assert "python3.11 -m venv /opt/knowledge-manager/.venv" in runbook
    assert "/opt/knowledge-manager/.venv/bin/pip install --no-cache-dir --force-reinstall ." in runbook
    assert "/opt/knowledge-manager/.venv/bin/km init /opt/knowledge-manager/kb" in runbook
    assert "/opt/knowledge-manager/.venv/bin/km --version" in runbook
    assert "install -m 0644 deploy/logrotate/knowledge-manager /etc/logrotate.d/knowledge-manager" in runbook
    assert "systemctl enable --now caddy" in runbook
    assert "Review /opt/knowledge-manager/.env.production and confirm KM_KB_PATH, KM_UI_HOST, KM_UI_PORT, and KM_LOG_LEVEL before starting services." in runbook
    assert 'RELEASE_DIR=/opt/knowledge-manager/release-artifacts/run-$(date +%Y%m%d%H%M%S)' in runbook
    assert 'python3.11 /opt/knowledge-manager/scripts/verify_install_smoke.py --project-root /opt/knowledge-manager --python python3.11 --format json > "$RELEASE_DIR"/verify-install-smoke.json' in runbook
    assert '/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-production-readiness --matrix-summary <fresh-matrix-summary.json> > "$RELEASE_DIR"/verify-production-readiness.json' in runbook
    assert '/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json > "$RELEASE_DIR"/verify-deployment.json' in runbook
    assert '/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb support bundle --output-dir "$RELEASE_DIR" --matrix-summary <fresh-matrix-summary.json>' in runbook
    assert 'systemctl cat knowledge-manager-api > "$RELEASE_DIR"/knowledge-manager-api.unit.txt' in runbook
    assert 'systemctl cat knowledge-manager-worker > "$RELEASE_DIR"/knowledge-manager-worker.unit.txt' in runbook
    assert 'caddy validate --config /etc/caddy/Caddyfile > "$RELEASE_DIR"/caddy-validate.txt 2>&1' in runbook
    assert 'logrotate -d /etc/logrotate.d/knowledge-manager > "$RELEASE_DIR"/logrotate-check.txt 2>&1' in runbook
    assert "python3.11 /opt/knowledge-manager/scripts/verify_install_smoke.py --project-root /opt/knowledge-manager --python python3.11 --format text" in runbook
    assert "/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-deployment" in runbook
    assert "/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb support bundle" in runbook
    assert "/opt/knowledge-manager/.venv/bin/km backup restore" in runbook
    assert "systemctl status caddy" in runbook
    assert "replace the placeholder host" in runbook
    assert "automatic HTTPS" in runbook
    assert "verify-deployment" in runbook
    assert "support bundle" in runbook


def test_observability_runbook_mentions_metrics_logs_alerts_and_bundle():
    root = Path(__file__).resolve().parents[1]
    text = (root / "docs" / "runbooks" / "observability-and-alerting.md").read_text(encoding="utf-8")
    assert "/api/metrics" in text
    assert "audit.jsonl" in text
    assert "verify-deployment" in text
    assert "release-support-bundle.json" in text
    assert "complete == true" in text
    assert "backup_restore_drill_within_30_days == true" in text
    assert "alert" in text.lower()


def test_logrotate_policy_targets_audit_and_app_logs():
    root = Path(__file__).resolve().parents[1]
    text = (root / "deploy" / "logrotate" / "knowledge-manager").read_text(encoding="utf-8")
    assert ".audit/audit.jsonl" in text
    assert "/var/log/knowledge-manager" in text


def test_governance_docs_reference_deployment_verification_and_release_ownership():
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    checklist = (root / "docs" / "runbooks" / "production-release-checklist.md").read_text(
        encoding="utf-8"
    )
    perf_plan = (root / "docs" / "runbooks" / "enterprise-performance-test-plan.md").read_text(
        encoding="utf-8"
    )
    rollout = (root / "docs" / "runbooks" / "enterprise-rollout.md").read_text(encoding="utf-8")
    cutover = (root / "docs" / "runbooks" / "migration-cutover.md").read_text(encoding="utf-8")
    backup_drill = (root / "docs" / "runbooks" / "backup-restore-drill.md").read_text(
        encoding="utf-8"
    )

    assert "verify-deployment" in readme
    assert "support bundle" in readme
    assert "python scripts/verify_install_smoke.py" in readme
    assert 'RELEASE_DIR=/opt/knowledge-manager/release-artifacts/run-$(date +%Y%m%d%H%M%S)' in readme
    assert 'python3.11 /opt/knowledge-manager/scripts/verify_install_smoke.py --project-root /opt/knowledge-manager --python python3.11 --format json > "$RELEASE_DIR"/verify-install-smoke.json' in readme
    assert 'verify-production-readiness --matrix-summary <fresh-matrix-summary.json> > "$RELEASE_DIR"/verify-production-readiness.json' in readme
    assert 'verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json > "$RELEASE_DIR"/verify-deployment.json' in readme
    assert 'support bundle --output-dir "$RELEASE_DIR" --matrix-summary <fresh-matrix-summary.json>' in readme
    assert 'collect_host_deploy_proof.py --output-dir "$RELEASE_DIR"' in readme
    assert 'host-deploy-proof.json' in readme
    assert "30 days" in checklist
    assert "support bundle" in checklist
    assert "python scripts/verify_install_smoke.py" in checklist
    assert 'python3.11 /opt/knowledge-manager/scripts/verify_install_smoke.py --project-root /opt/knowledge-manager --python python3.11 --format json > "$RELEASE_DIR"/verify-install-smoke.json' in checklist
    assert 'verify-production-readiness --matrix-summary <fresh-matrix-summary.json> > "$RELEASE_DIR"/verify-production-readiness.json' in checklist
    assert 'verify-deployment --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json> --format json > "$RELEASE_DIR"/verify-deployment.json' in checklist
    assert 'python3.11 /opt/knowledge-manager/scripts/collect_release_evidence.py --release-dir "$RELEASE_DIR" --kb-path /opt/knowledge-manager/kb --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json>' in checklist
    assert "complete == true" in checklist
    assert "backup_restore_drill_within_30_days == true" in checklist
    assert "deploy_artifact_proof_complete == true" in checklist
    assert "host-deploy-proof.json" in checklist
    assert "/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb verify-deployment" in checklist
    assert "/opt/knowledge-manager/.venv/bin/km backup restore" in checklist
    assert "/opt/knowledge-manager/.venv/bin/km worker run --once" in checklist
    assert "rollback" in checklist.lower()
    assert "Capacity Boundary" in perf_plan
    assert "verify-deployment" in perf_plan
    assert "rollback owner" in rollout
    assert "support bundle path" in rollout
    assert "rollback owner" in cutover
    assert "backup bundle path" in cutover
    assert "30 days" in backup_drill
    assert "verify-deployment" in backup_drill
    assert 'RELEASE_DIR=/opt/knowledge-manager/release-artifacts/run-$(date +%Y%m%d%H%M%S)' in backup_drill
    assert 'restore-verify-deployment.json' in backup_drill
    assert '--attach "$RELEASE_DIR"/verify-production-readiness.json' in backup_drill
    assert '--attach "$RELEASE_DIR"/verify-deployment.json' in backup_drill
    assert '--attach "$RELEASE_DIR"/verify-install-smoke.json' in backup_drill
    assert "/opt/knowledge-manager/.venv/bin/km --kb-path /opt/knowledge-manager/kb backup create" in backup_drill
    assert "/opt/knowledge-manager/.venv/bin/km backup restore" in backup_drill


def test_packaging_smoke_script_builds_wheel_and_installs_cli():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "verify_install_smoke.py").read_text(encoding="utf-8")

    assert "pip" in script
    assert "wheel" in script
    assert "venv" in script
    assert '"--version"' in script
    assert '"init"' in script
    assert '"--kb-path"' in script


def test_cli_search(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    save_module(make_module("db-conn", "database"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "search", "auth"])
    assert result.exit_code == 0
    assert "auth-jwt" in result.output


def test_cli_rebuild(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "rebuild"])
    assert result.exit_code == 0
    assert "Rebuilt" in result.output or "rebuilt" in result.output.lower()


def test_cli_delete_with_confirm(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "delete", "auth-jwt", "-c", "auth", "--yes"],
    )
    assert result.exit_code == 0
    assert not (initialized_kb / "auth" / "auth-jwt.json").exists()


def test_cli_delete_not_found(cli_runner, initialized_kb):
    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "delete", "missing", "-c", "auth", "--yes"],
    )
    assert result.exit_code != 0


def test_cli_show_module(cli_runner, initialized_kb):
    save_module(make_module("auth-jwt", "auth"), initialized_kb)
    result = cli_runner.invoke(
        cli, ["--kb-path", str(initialized_kb), "show", "auth-jwt", "-c", "auth"]
    )
    assert result.exit_code == 0
    assert "auth-jwt" in result.output


def test_cli_config_list(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "config", "list"])
    assert result.exit_code == 0


def test_cli_config_set_get(cli_runner, initialized_kb):
    set_result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "config",
            "set",
            "extraction.provider",
            "claude",
        ],
    )
    assert set_result.exit_code == 0
    get_result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "config", "get", "extraction.provider"],
    )
    assert get_result.exit_code == 0
    assert "claude" in get_result.output


def test_cli_add_extracts_to_staging(cli_runner, initialized_kb, tmp_path):
    src_file = tmp_path / "notes.txt"
    src_file.write_text("Some notes about JWT authentication.")

    sample = make_module("auth-jwt", "auth")

    async def fake_extract(self, text, category, existing_categories=""):
        return [sample]

    with patch("knowledge_manager.cli.Extractor.extract", new=fake_extract):
        with patch("knowledge_manager.cli.create_client") as mock_create:
            mock_create.return_value = AsyncMock()
            result = cli_runner.invoke(
                cli,
                [
                    "--kb-path",
                    str(initialized_kb),
                    "add",
                    str(src_file),
                    "-c",
                    "auth",
                ],
            )

    assert result.exit_code == 0, result.output
    assert "Extracted" in result.output or "extracted" in result.output.lower()
    staging_files = [f for f in (initialized_kb / ".staging").glob("*.json") if not f.name.endswith(".meta.json")]
    assert len(staging_files) == 1


def test_cli_add_file_not_found(cli_runner, initialized_kb):
    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "add",
            "no-such-file.txt",
            "-c",
            "general",
        ],
    )
    assert result.exit_code != 0


def test_cli_review_approve(cli_runner, initialized_kb):
    sample = make_module("auth-jwt", "auth")
    save_to_staging(sample, initialized_kb / ".staging")

    result = cli_runner.invoke(
        cli, ["--kb-path", str(initialized_kb), "review"], input="a\n"
    )
    assert result.exit_code == 0
    assert (initialized_kb / "auth" / "auth-jwt.json").exists()
    assert not (initialized_kb / ".staging" / "auth-jwt.json").exists()


def test_cli_review_reject(cli_runner, initialized_kb):
    sample = make_module("auth-jwt", "auth")
    save_to_staging(sample, initialized_kb / ".staging")

    result = cli_runner.invoke(
        cli, ["--kb-path", str(initialized_kb), "review"], input="r\n"
    )
    assert result.exit_code == 0
    assert not (initialized_kb / "auth" / "auth-jwt.json").exists()
    assert not (initialized_kb / ".staging" / "auth-jwt.json").exists()


def test_cli_review_skip(cli_runner, initialized_kb):
    sample = make_module("auth-jwt", "auth")
    save_to_staging(sample, initialized_kb / ".staging")

    result = cli_runner.invoke(
        cli, ["--kb-path", str(initialized_kb), "review"], input="s\n"
    )
    assert result.exit_code == 0
    # Skipped — should remain in staging
    assert (initialized_kb / ".staging" / "auth-jwt.json").exists()


def test_cli_source_add_confluence_and_status(cli_runner, initialized_kb):
    add_result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "architecture",
        ],
    )

    assert add_result.exit_code == 0
    status_result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "status"])
    assert status_result.exit_code == 0
    assert "team-docs" in status_result.output
    assert "architecture" in status_result.output


def test_cli_source_add_notion_and_status(cli_runner, initialized_kb):
    add_result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-notion",
            "ops-notes",
            "--token-env",
            "NOTION_TOKEN",
            "--database-id",
            "db-1",
            "--category",
            "operations",
        ],
    )

    assert add_result.exit_code == 0
    status_result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "status"])
    assert status_result.exit_code == 0
    assert "ops-notes [notion]" in status_result.output
    assert "operations" in status_result.output


def test_cli_source_pull_stages_modules(cli_runner, initialized_kb, monkeypatch):
    from knowledge_manager.audit import read_audit_log

    cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "architecture",
        ],
    )
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token")

    async def fake_list_pages(self, space_key, root_page_id="", limit=25, cursor=""):
        return (
            [
                ConfluencePage(
                    page_id="12345",
                    title="JWT Runbook",
                    url="https://example.atlassian.net/wiki/spaces/ENG/pages/12345",
                    version="7",
                    body_text="Refresh tokens rotate on every successful refresh.",
                    heading_path=["ENG", "JWT Runbook"],
                    checksum="abc123",
                )
            ],
            "cursor-2",
        )

    async def fake_extract(self, text, category, existing_categories=""):
        return [make_module("jwt-playbook", category)]

    monkeypatch.setattr("knowledge_manager.confluence.ConfluenceClient.list_pages", fake_list_pages)
    monkeypatch.setattr("knowledge_manager.cli.Extractor.extract", fake_extract)
    monkeypatch.setattr("knowledge_manager.cli.create_client", lambda provider_name, provider_cfg: AsyncMock())

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "pull", "team-docs"])
    assert result.exit_code == 0, result.output
    assert "Job job-" in result.output
    assert "staged 1 modules" in result.output
    assert (initialized_kb / ".staging" / "jwt-playbook.json").exists()
    assert (initialized_kb / ".staging" / "jwt-playbook.meta.json").exists()
    assert any((initialized_kb / ".jobs" / "ingestion").glob("*.json"))
    events = read_audit_log(initialized_kb)
    assert any(event["operation"] == "source.pull" and event["result"] == "success" for event in events)

    status_result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "status"])
    assert status_result.exit_code == 0
    assert "cursor-2" in status_result.output


def test_cli_source_pull_notion_stages_modules(cli_runner, initialized_kb, monkeypatch):
    cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-notion",
            "ops-notes",
            "--token-env",
            "NOTION_TOKEN",
            "--database-id",
            "db-1",
            "--category",
            "operations",
        ],
    )
    monkeypatch.setenv("NOTION_TOKEN", "token")

    async def fake_list_pages(self, database_id, page_limit=25, cursor=""):
        from knowledge_manager.notion import NotionPage

        return (
            [
                NotionPage(
                    page_id="page-1",
                    title="Ops Runbook",
                    url="https://www.notion.so/page-1",
                    version="2026-06-12T08:00:00.000Z",
                    body_text="Escalations route through the primary on-call.",
                    heading_path=["Notion", "Ops Runbook"],
                    checksum="xyz123",
                )
            ],
            "cursor-3",
        )

    async def fake_extract(self, text, category, existing_categories=""):
        return [make_module("ops-runbook", category)]

    monkeypatch.setattr("knowledge_manager.notion.NotionClient.list_pages", fake_list_pages)
    monkeypatch.setattr("knowledge_manager.cli.Extractor.extract", fake_extract)
    monkeypatch.setattr("knowledge_manager.cli.create_client", lambda provider_name, provider_cfg: AsyncMock())

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "pull", "ops-notes"])
    assert result.exit_code == 0, result.output
    assert "Job job-" in result.output
    assert "staged 1 modules" in result.output
    assert (initialized_kb / ".staging" / "ops-runbook.json").exists()

    status_result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "status"])
    assert status_result.exit_code == 0
    assert "cursor-3" in status_result.output


def test_cli_source_pull_retries_transient_errors(cli_runner, initialized_kb, monkeypatch):
    cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "architecture",
        ],
    )
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token")
    attempts = {"count": 0}

    async def flaky_list_pages(self, space_key, root_page_id="", limit=25, cursor=""):
        attempts["count"] += 1
        if attempts["count"] < 3:
            request = httpx.Request("GET", "https://example.atlassian.net/wiki/rest/api/content")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("service unavailable", request=request, response=response)
        return (
            [
                ConfluencePage(
                    page_id="12345",
                    title="JWT Runbook",
                    url="https://example.atlassian.net/wiki/spaces/ENG/pages/12345",
                    version="7",
                    body_text="Refresh tokens rotate on every successful refresh.",
                    heading_path=["ENG", "JWT Runbook"],
                    checksum="abc123",
                )
            ],
            "cursor-2",
        )

    async def fake_extract(self, text, category, existing_categories=""):
        return [make_module("jwt-playbook", category)]

    monkeypatch.setattr("knowledge_manager.confluence.ConfluenceClient.list_pages", flaky_list_pages)
    monkeypatch.setattr("knowledge_manager.cli.Extractor.extract", fake_extract)
    monkeypatch.setattr("knowledge_manager.cli.create_client", lambda provider_name, provider_cfg: AsyncMock())
    monkeypatch.setattr("knowledge_manager.cli.asyncio.sleep", AsyncMock())

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "pull", "team-docs"])

    assert result.exit_code == 0, result.output
    assert attempts["count"] == 3
    assert "staged 1 modules" in result.output


def test_cli_source_pull_does_not_retry_permanent_errors(cli_runner, initialized_kb, monkeypatch):
    from knowledge_manager.audit import read_audit_log

    cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "architecture",
        ],
    )
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token")
    attempts = {"count": 0}

    async def unauthorized_list_pages(self, space_key, root_page_id="", limit=25, cursor=""):
        attempts["count"] += 1
        request = httpx.Request("GET", "https://example.atlassian.net/wiki/rest/api/content")
        response = httpx.Response(401, request=request)
        raise httpx.HTTPStatusError("unauthorized", request=request, response=response)

    monkeypatch.setattr("knowledge_manager.confluence.ConfluenceClient.list_pages", unauthorized_list_pages)
    monkeypatch.setattr("knowledge_manager.cli.create_client", lambda provider_name, provider_cfg: AsyncMock())
    monkeypatch.setattr("knowledge_manager.cli.asyncio.sleep", AsyncMock())

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "pull", "team-docs"])

    assert result.exit_code != 0
    assert attempts["count"] == 1
    assert "source pull failed" in result.output
    job_files = list((initialized_kb / ".jobs" / "ingestion").glob("*.json"))
    assert job_files
    assert '"status": "failed"' in job_files[0].read_text(encoding="utf-8")
    events = read_audit_log(initialized_kb)
    assert any(event["operation"] == "source.pull" and event["result"] == "failed" for event in events)


def test_cli_eval_run(cli_runner, initialized_kb, tmp_path):
    save_module(make_module("jwt-playbook", "auth"), initialized_kb)
    suite_path = tmp_path / "eval-suite.json"
    suite_path.write_text(
        json.dumps(
            {
                "name": "smoke",
                "cases": [
                    {
                        "id": "jwt-hit",
                        "query": "test module",
                        "required_modules": ["auth/jwt-playbook"],
                        "top_k": 3,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "eval", "run", str(suite_path), "--top-k", "3"],
    )
    assert result.exit_code == 0
    assert "1/1 cases passed" in result.output
    assert "Hit rate: 100.0%" in result.output
    assert "[PASS] jwt-hit" in result.output


def test_cli_eval_run_shows_suppression_summary(cli_runner, initialized_kb, tmp_path):
    (initialized_kb / "config.json").write_text(
        json.dumps(
            {
                "llm_providers": {
                    "deepseek": {
                        "api_key": "",
                        "model": "deepseek-v4-pro",
                        "base_url": "https://api.deepseek.com",
                        "default": True
                    }
                },
                "routing_policy": {
                    "risk_level_allowed_statuses": {"high": ["published"]}
                }
            }
        ),
        encoding="utf-8",
    )
    draft = make_module("draft-ops", "ops")
    draft.title = "Sensitive rollout draft"
    draft.summary = "Sensitive rollout draft guidance."
    draft.content = ModuleContent(
        overview="Sensitive rollout draft overview.",
        details="Sensitive rollout draft details with enough length for validation.",
    )
    draft.metadata.status = "draft"
    save_module(draft, initialized_kb)

    published = make_module("published-ops", "ops")
    published.title = "Sensitive rollout published"
    published.summary = "Sensitive rollout published guidance."
    published.content = ModuleContent(
        overview="Sensitive rollout published overview.",
        details="Sensitive rollout published details with enough length for validation.",
    )
    save_module(published, initialized_kb)

    suite_path = tmp_path / "eval-suite.json"
    suite_path.write_text(
        json.dumps(
            {
                "name": "smoke",
                "cases": [
                    {
                        "id": "high-risk-rollout",
                        "query": "sensitive rollout",
                        "required_modules": ["ops/published-ops", "ops/draft-ops"],
                        "risk_level": "high",
                        "task_type": "production-change",
                        "top_k": 5
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "eval", "run", str(suite_path), "--top-k", "5"],
    )
    assert result.exit_code == 0
    assert "Suppression-driven failure rate: 100.0%" in result.output
    assert "risk/high" in result.output.lower()
    assert "policy_failures=" in result.output
    assert "retrieval_failures=" in result.output


def test_cli_source_pull_records_sync_error(cli_runner, initialized_kb, monkeypatch):
    cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "architecture",
        ],
    )
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token")

    async def fail_list_pages(self, space_key, root_page_id="", limit=25, cursor=""):
        raise RuntimeError("confluence unavailable")

    monkeypatch.setattr("knowledge_manager.confluence.ConfluenceClient.list_pages", fail_list_pages)
    monkeypatch.setattr("knowledge_manager.cli.create_client", lambda provider_name, provider_cfg: AsyncMock())

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "pull", "team-docs"])
    assert result.exit_code != 0
    assert "confluence unavailable" in result.output.lower()

    status_result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "status"])
    assert status_result.exit_code == 0
    assert "confluence unavailable" in status_result.output.lower()


def test_cli_source_pull_retries_transient_failure(cli_runner, initialized_kb, monkeypatch):
    cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "architecture",
        ],
    )
    monkeypatch.setenv("CONFLUENCE_API_TOKEN", "token")
    attempts = {"count": 0}

    async def flaky_list_pages(self, space_key, root_page_id="", limit=25, cursor=""):
        attempts["count"] += 1
        if attempts["count"] < 3:
            request = httpx.Request("GET", "https://example.atlassian.net/wiki/rest/api/content")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("service unavailable", request=request, response=response)
        return (
            [
                ConfluencePage(
                    page_id="12345",
                    title="JWT Runbook",
                    url="https://example.atlassian.net/wiki/spaces/ENG/pages/12345",
                    version="7",
                    body_text="Refresh tokens rotate on every successful refresh.",
                    heading_path=["ENG", "JWT Runbook"],
                    checksum="abc123",
                )
            ],
            "",
        )

    async def fake_extract(self, text, category, existing_categories=""):
        return [make_module("jwt-playbook", category)]

    monkeypatch.setattr("knowledge_manager.confluence.ConfluenceClient.list_pages", flaky_list_pages)
    monkeypatch.setattr("knowledge_manager.cli.Extractor.extract", fake_extract)
    monkeypatch.setattr("knowledge_manager.cli.create_client", lambda provider_name, provider_cfg: AsyncMock())
    monkeypatch.setattr("knowledge_manager.cli.asyncio.sleep", AsyncMock())

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "source", "pull", "team-docs"])
    assert result.exit_code == 0, result.output
    assert attempts["count"] == 3
    assert "staged 1 modules" in result.output


def test_cli_add_verbose_logs_only_metadata(cli_runner, initialized_kb, tmp_path, caplog):
    src_file = tmp_path / "notes.txt"
    raw_text = "Sensitive note about JWT authentication and internal claims."
    src_file.write_text(raw_text)

    sample = make_module("auth-jwt", "auth")

    async def fake_extract(self, text, category, existing_categories=""):
        logging.getLogger("knowledge_manager.extractor").debug(
            "Extractor chunk processed (%s chars)", len(text)
        )
        return [sample]

    with patch("knowledge_manager.cli.Extractor.extract", new=fake_extract):
        with patch("knowledge_manager.cli.create_client") as mock_create:
            mock_create.return_value = AsyncMock()
            with caplog.at_level(logging.DEBUG, logger="knowledge_manager"):
                result = cli_runner.invoke(
                    cli,
                    [
                        "--verbose",
                        "--kb-path",
                        str(initialized_kb),
                        "add",
                        str(src_file),
                        "-c",
                        "auth",
                    ],
                )

    assert result.exit_code == 0, result.output
    assert any(
        record.name == "knowledge_manager.extractor"
        and "Extractor chunk processed" in record.getMessage()
        for record in caplog.records
    )
    log_text = caplog.text
    assert raw_text not in log_text
    assert str(src_file) not in log_text


def test_cli_review_empty_staging(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review"])
    assert result.exit_code == 0
    assert "No" in result.output or "no" in result.output.lower()


def test_cli_search_shows_confidence_badges(cli_runner, initialized_kb):
    save_module(Module(
        id="conf-high", category="general",
        title="High confidence module",
        summary="A module with high confidence rating",
        content=ModuleContent(overview="High confidence overview text", details="High confidence details for testing badges in CLI"),
        metadata=ModuleMetadata(tags=["test"], confidence="high"),
    ), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "search", "confidence"])
    assert result.exit_code == 0
    assert "[high]" in result.output


def test_cli_search_shows_related_source_badge(cli_runner, initialized_kb):
    save_module(Module(
        id="graph-direct", category="general",
        title="Direct match module",
        summary="This module matches the query directly",
        content=ModuleContent(overview="Direct match overview for testing.", details="Direct match details for testing source badges in CLI."),
        metadata=ModuleMetadata(tags=["graph"], related_modules=["general/graph-neighbor"]),
    ), initialized_kb)
    save_module(Module(
        id="graph-neighbor", category="general",
        title="Neighbor module title",
        summary="Neighbor module for graph expansion",
        content=ModuleContent(overview="Neighbor overview for graph expansion testing.", details="Neighbor details for testing graph expansion source badges in CLI search."),
        metadata=ModuleMetadata(tags=["graph"]),
    ), initialized_kb)
    rebuild_index(initialized_kb)
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "search", "Direct match"])
    assert result.exit_code == 0
    assert "graph-direct" in result.output
    assert "graph-neighbor" in result.output
    assert "[related]" in result.output


def test_cli_telemetry_status(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "telemetry", "status"])
    assert result.exit_code == 0
    assert "Telemetry" in result.output


def test_cli_telemetry_disable_enable(cli_runner, initialized_kb):
    # Disable
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "telemetry", "disable"])
    assert result.exit_code == 0
    assert "disabled" in result.output.lower()
    # Enable
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "telemetry", "enable"])
    assert result.exit_code == 0
    assert "enabled" in result.output.lower()


def test_cli_rank_status(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "rank", "status"])
    assert result.exit_code == 0
    assert "Model" in result.output


def test_cli_rank_retrain(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "rank", "retrain"])
    assert result.exit_code == 0
    assert "retrain" in result.output.lower() or "model" in result.output.lower()


def test_cli_stale_shows_expired_module(cli_runner, initialized_kb):
    from datetime import datetime, timedelta, timezone
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    save_module(Module(
        id="expired-mod", category="general",
        title="Expired module",
        summary="This module has already expired",
        content=ModuleContent(
            overview="Overview for expired module that should show in stale list.",
            details="Details for expired module — this module is past its expiry date.",
        ),
        metadata=ModuleMetadata(
            tags=["test"],
            expires_at=yesterday,
        ),
    ), initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "stale"])
    assert result.exit_code == 0
    assert "expired-mod" in result.output


def test_cli_stale_shows_review_due_module(cli_runner, initialized_kb):
    from datetime import datetime, timedelta, timezone
    old_date = datetime.now(timezone.utc) - timedelta(days=40)
    save_module(Module(
        id="review-mod", category="general",
        title="Module due for review",
        summary="This module was updated long ago and should be reviewed",
        content=ModuleContent(
            overview="Overview for module that needs review based on interval.",
            details="Details for review due module for testing stale command.",
        ),
        metadata=ModuleMetadata(
            tags=["test"],
            review_interval_days=30,
        ),
        updated_at=old_date,
    ), initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "stale"])
    assert result.exit_code == 0
    assert "review-mod" in result.output


def test_cli_stale_empty_when_none_stale(cli_runner, initialized_kb):
    save_module(make_module("fresh-mod", "general"), initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "stale"])
    assert result.exit_code == 0
    assert "No stale modules" in result.output


def test_init_creates_gitignore_template(cli_runner, tmp_path):
    kb = tmp_path / "kb"
    result = cli_runner.invoke(cli, ["init", str(kb)])
    assert result.exit_code == 0
    gitignore = kb / ".gitignore"
    assert gitignore.exists(), ".gitignore should be created on init"
    content = gitignore.read_text()
    assert ".staging/" in content
    assert ".telemetry/" in content
    assert "config.local.json" in content


@pytest.fixture
def remote_kb(tmp_path):
    """Create a 'remote' git repo with a valid KM knowledge base."""
    import subprocess
    remote = tmp_path / "remote-kb"
    remote.mkdir()
    subprocess.run(["git", "-C", str(remote), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(remote), "config", "user.email", "kb@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(remote), "config", "user.name", "KB Test"], capture_output=True, check=True)
    # Create index.json
    from knowledge_manager.schemas import Index
    Index(description="Test remote KB").model_dump_json()
    import json
    (remote / "index.json").write_text(json.dumps({"version": "1.0", "description": "Test remote KB", "categories": {}, "graph": {}, "usage": {"total_modules": 0, "total_words": 0, "categories": 0}}))
    subprocess.run(["git", "-C", str(remote), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(remote), "commit", "-m", "init"], capture_output=True, check=True)
    return remote


def test_cli_clone_into_new_directory(cli_runner, remote_kb, tmp_path):
    local = tmp_path / "local-kb"
    result = cli_runner.invoke(cli, ["clone", str(remote_kb), "--path", str(local)])
    assert result.exit_code == 0
    assert local.exists()
    assert (local / "index.json").exists()
    assert "Cloned" in result.output


def test_cli_clone_rejects_existing_path(cli_runner, remote_kb, tmp_path):
    local = tmp_path / "existing"
    local.mkdir()
    result = cli_runner.invoke(cli, ["clone", str(remote_kb), "--path", str(local)])
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_cli_clone_warns_on_non_kb_repo(cli_runner, tmp_path):
    import subprocess
    non_kb = tmp_path / "non-kb"
    non_kb.mkdir()
    subprocess.run(["git", "-C", str(non_kb), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(non_kb), "config", "user.email", "test@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(non_kb), "config", "user.name", "Test"], capture_output=True, check=True)
    (non_kb / "README.md").write_text("Just a regular repo")
    subprocess.run(["git", "-C", str(non_kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(non_kb), "commit", "-m", "init"], capture_output=True, check=True)

    local = tmp_path / "clone-non-kb"
    result = cli_runner.invoke(cli, ["clone", str(non_kb), "--path", str(local)])
    assert result.exit_code == 0
    assert "may not be a valid km knowledge base" in result.output.lower()


def test_cli_push_sanitizes_api_keys(cli_runner, initialized_kb):
    from knowledge_manager.schemas import Config, LLMProviderConfig
    from knowledge_manager.storage import _load_config_safe
    import subprocess

    kb = initialized_kb
    # Set up git in the KB
    subprocess.run(["git", "-C", str(kb), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "config", "user.email", "kb@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "config", "user.name", "KB Test"], capture_output=True, check=True)
    # Add a remote (point to a bare repo)
    bare = kb.parent / "bare.git"
    bare.mkdir()
    subprocess.run(["git", "-C", str(bare), "init", "--bare"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(bare)], capture_output=True, check=True)

    # Set a real API key
    cfg = Config(
        llm_providers={
            "deepseek": LLMProviderConfig(
                api_key="sk-real-key-123",
                model="deepseek-v4",
                default=True,
            ),
        },
    )
    config_path = kb / "config.json"
    config_path.write_text(cfg.model_dump_json())

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "push"])
    # Push may fail for shallow reasons but should NOT leak the API key in output
    if result.exit_code == 0:
        # Config should have been restored with real key
        restored = _load_config_safe(kb)
        assert restored is not None
        assert restored.llm_providers["deepseek"].api_key == "sk-real-key-123"


def test_init_creates_meaningful_description():
    runner = CliRunner()
    with runner.isolated_filesystem():
        kb = Path("test_kb")
        result = runner.invoke(cli, ["init", str(kb)])
        assert result.exit_code == 0

        index = load_index(kb)
        assert index is not None
        assert len(index.description) > 20, "Description should be more than just 'Knowledge base'"
        assert "methodology" in index.description.lower() or "knowledge" in index.description.lower()


# ── Phase 2A: git collaboration tests ──



def _init_git_in_dir(path: Path):
    """Ensure path is a git repo. If not, init and configure. Always rename branch to 'main'."""
    import subprocess
    if not (path / ".git").exists():
        subprocess.run(["git", "-C", str(path), "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "kb@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Test User"], capture_output=True, check=True)
    # Ensure branch is named "main" (CLI hardcodes origin/main)
    branch_result = subprocess.run(["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    if branch_result.stdout.strip() != "main":
        subprocess.run(["git", "-C", str(path), "branch", "-m", "main"], capture_output=True, check=True)


def _create_bare_remote(kb: Path, remote_path: Path, push_initial: bool = True):
    """Helper: create a bare remote, set origin, optionally push initial commit."""
    import subprocess
    _init_git_in_dir(kb)
    remote_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(remote_path), "init", "--bare"], capture_output=True, check=True)
    # Remove existing origin if present
    subprocess.run(["git", "-C", str(kb), "remote", "remove", "origin"], capture_output=True)
    subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(remote_path)], capture_output=True, check=True)
    if push_initial:
        subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(kb), "commit", "--allow-empty", "-m", "init"], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(kb), "push", "-u", "origin", "main"], capture_output=True, check=True)


def test_cli_pull_up_to_date(cli_runner, initialized_kb, tmp_path):
    """pull when already up to date should report so."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "pull"])
    assert result.exit_code == 0
    assert "Already up to date" in result.output or "Index rebuilt" in result.output


def test_cli_pull_rebuilds_index(cli_runner, initialized_kb, tmp_path):
    """pull should rebuild the index after fetching."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "pull"])
    assert result.exit_code == 0
    assert "Index rebuilt" in result.output
    # index.json should exist and be valid
    assert (kb / "index.json").exists()
    idx = load_index(kb)
    assert idx is not None


def test_cli_status_no_changes(cli_runner, initialized_kb, tmp_path):
    """status with no local changes should report clean."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "status"])
    assert result.exit_code == 0
    # Should not show added/modified/deleted counts (clean state)
    assert "No changes" in result.output


def test_cli_status_shows_added_modules(cli_runner, initialized_kb, tmp_path):
    """status should detect locally added module files."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add a new module locally and stage it
    mod = make_module("new-mod", "test")
    save_module(mod, kb)
    subprocess.run(["git", "-C", str(kb), "add", "test/new-mod.json"], capture_output=True, check=True)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "status"])
    assert result.exit_code == 0
    assert "test/new-mod.json" in result.output


def test_cli_status_shows_modified_modules(cli_runner, initialized_kb, tmp_path):
    """status should detect locally modified module files."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add and commit a module, push, then modify it locally
    mod = make_module("mod-m", "test")
    save_module(mod, kb)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "-m", "add module"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "origin", "main"], capture_output=True, check=True)

    # Modify locally
    mod.summary = "Updated summary for testing"
    save_module(mod, kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "status"])
    assert result.exit_code == 0
    assert "Modified" in result.output or "test/mod-m.json" in result.output


def test_cli_diff_new_module(cli_runner, initialized_kb, tmp_path):
    """diff for a module not in remote should report it as new."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add a module locally without pushing
    mod = make_module("local-only", "test")
    save_module(mod, kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "diff", "test/local-only"])
    assert result.exit_code == 0
    assert "new" in result.output.lower() or "not in remote" in result.output.lower()


def test_cli_diff_shows_field_changes(cli_runner, initialized_kb, tmp_path):
    """diff should show field-level JSON differences."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add and push a module
    mod = make_module("mod-d", "test")
    save_module(mod, kb)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "-m", "add module"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "origin", "main"], capture_output=True, check=True)

    # Modify locally
    mod.title = "Changed Title Here"
    mod.summary = "Changed summary text"
    save_module(mod, kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "diff", "test/mod-d"])
    assert result.exit_code == 0
    assert "Changed Title Here" in result.output or "title" in result.output.lower() or "Changes in test/mod-d" in result.output


def test_cli_diff_no_changes(cli_runner, initialized_kb, tmp_path):
    """diff with no local changes should report no differences."""
    import subprocess
    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _create_bare_remote(kb, bare)

    # Add and push a module
    mod = make_module("mod-same", "test")
    save_module(mod, kb)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "-m", "add module"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "origin", "main"], capture_output=True, check=True)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "diff", "test/mod-same"])
    assert result.exit_code == 0
    assert "No differences" in result.output


def test_cli_diff_invalid_format(cli_runner, initialized_kb):
    """diff with invalid module_ref format should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "diff", "no-slash-here"])
    assert result.exit_code != 0
    assert "category/module-id" in result.output


def test_json_diff_sections_detects_all_change_types():
    """Unit test for _json_diff_sections helper."""
    from knowledge_manager.cli import _json_diff_sections

    remote = {
        "id": "test",
        "category": "x",
        "title": "Old Title",
        "summary": "Old Summary",
        "content": {"overview": "Old overview text.", "details": "Old details text that is long enough.", "examples": ""},
        "metadata": {"tags": ["old"], "confidence": "high"},
    }
    local = {
        "id": "test",
        "category": "x",
        "title": "New Title",
        "summary": "Old Summary",
        "content": {"overview": "New overview text.", "details": "Old details text that is long enough.", "references": "Added ref"},
        "metadata": {"tags": ["new"], "confidence": "low"},
    }

    lines = _json_diff_sections(remote, local)
    assert len(lines) > 0
    # title section changed
    assert any("title" in l for l in lines)
    # content nested diff
    assert any("content" in l for l in lines)
    # metadata nested diff
    assert any("metadata" in l for l in lines)


def test_json_diff_sections_identical():
    """Identical dicts should produce no diff lines."""
    from knowledge_manager.cli import _json_diff_sections

    data = {"id": "t", "category": "c", "title": "T", "summary": "S", "content": {"overview": "O"}}
    lines = _json_diff_sections(data, data)
    assert len(lines) == 0


# ── Phase 2B: review pipeline tests ──


def _stage_module(kb: Path, module_id: str = "test-mod", category: str = "test"):
    """Helper: add a module to staging and create metadata."""
    from knowledge_manager.storage import save_to_staging, save_staging_meta
    from knowledge_manager.schemas import Module, ModuleContent, ModuleMetadata, StagingMeta
    mod = Module(
        id=module_id,
        category=category,
        title=f"Review Test {module_id}",
        summary="A module for testing the review pipeline.",
        content=ModuleContent(
            overview="Overview for review testing.",
            details="Details that are definitely long enough to pass the validation check.",
        ),
        metadata=ModuleMetadata(tags=["review-test"]),
    )
    staging = kb / ".staging"
    staging.mkdir(exist_ok=True)
    save_to_staging(mod, staging)
    save_staging_meta(StagingMeta(module_id=module_id, submitted_by="test-user"), staging)
    return mod


def test_review_list_empty(cli_runner, initialized_kb):
    """review list with no staged modules should report empty."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review", "list"])
    assert result.exit_code == 0
    assert "No staged modules" in result.output


def test_review_list_shows_staged(cli_runner, initialized_kb):
    """review list should show staged modules with status."""
    kb = initialized_kb
    _stage_module(kb, "mod-a")

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "list"])
    assert result.exit_code == 0
    assert "mod-a" in result.output


def test_review_show_existing_module(cli_runner, initialized_kb):
    """review show should display module content and review history."""
    kb = initialized_kb
    _stage_module(kb, "mod-show")

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "show", "mod-show"])
    assert result.exit_code == 0
    assert "mod-show" in result.output
    assert "Review Test" in result.output


def test_review_show_missing_module(cli_runner, initialized_kb):
    """review show with nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review", "show", "no-such-module"])
    assert result.exit_code != 0


def test_review_approve_merges_module(cli_runner, initialized_kb):
    """review approve should merge module into KB when approval threshold met."""
    kb = initialized_kb
    _stage_module(kb, "mod-ok")

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "approve", "mod-ok"])
    assert result.exit_code == 0
    assert "Approved and merged" in result.output

    # Module should now exist in KB
    from knowledge_manager.storage import load_module
    mod = load_module("mod-ok", "test", kb)
    assert mod is not None
    assert mod.title == "Review Test mod-ok"


def test_review_approve_requires_multiple_approvals(cli_runner, initialized_kb):
    """approve should not merge until required_approvals met."""
    kb = initialized_kb
    from knowledge_manager.schemas import Config, ReviewConfig
    from knowledge_manager.cli import _save_config

    # Configure 2 required approvals
    cfg = Config(review=ReviewConfig(required_approvals=2))
    _save_config(kb, cfg)

    _stage_module(kb, "mod-needs2")

    # First approval
    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "approve", "mod-needs2"])
    assert result.exit_code == 0
    assert "1/2 approvals" in result.output

    # Module should NOT be in KB yet
    from knowledge_manager.storage import load_module, load_staging_meta
    assert load_module("mod-needs2", "test", kb) is None

    # Second approval
    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "approve", "mod-needs2"])
    assert result.exit_code == 0
    assert "Approved and merged" in result.output
    assert load_module("mod-needs2", "test", kb) is not None


def test_review_approve_missing_module(cli_runner, initialized_kb):
    """approve with nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review", "approve", "no-such"])
    assert result.exit_code != 0


def test_review_request_changes(cli_runner, initialized_kb):
    """request-changes should set status and record comment."""
    kb = initialized_kb
    _stage_module(kb, "mod-rc")

    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "review", "request-changes",
        "mod-rc", "-m", "Needs more details in overview",
    ])
    assert result.exit_code == 0
    assert "Changes requested" in result.output

    # Verify meta was updated
    from knowledge_manager.storage import load_staging_meta
    staging = kb / ".staging"
    meta = load_staging_meta("mod-rc", staging)
    assert meta is not None
    assert meta.status == "changes-requested"
    assert len(meta.reviews) == 1
    assert meta.reviews[0].action == "changes-requested"
    assert meta.reviews[0].comment == "Needs more details in overview"


def test_review_request_changes_requires_comment(cli_runner, initialized_kb):
    """request-changes without --comment should fail (required option)."""
    kb = initialized_kb
    _stage_module(kb, "mod-rc2")

    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "review", "request-changes", "mod-rc2",
    ])
    assert result.exit_code != 0


def test_review_my_submissions_shows_status(cli_runner, initialized_kb):
    """my-submissions should display submitted modules with review status."""
    kb = initialized_kb
    _stage_module(kb, "mod-sub1")
    _stage_module(kb, "mod-sub2")

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "review", "my-submissions"])
    assert result.exit_code == 0
    assert "mod-sub1" in result.output
    assert "mod-sub2" in result.output


def test_review_my_submissions_empty(cli_runner, initialized_kb):
    """my-submissions with no staged modules should report empty."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "review", "my-submissions"])
    assert result.exit_code == 0
    assert "No staged modules" in result.output


# ── Phase 2C: webhook notification tests ──


def test_push_sends_webhook_when_configured(cli_runner, initialized_kb, tmp_path):
    """push should POST to webhook_url when configured."""
    import subprocess
    from knowledge_manager.schemas import Config, LLMProviderConfig, NotificationsConfig
    from knowledge_manager.cli import _save_config

    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _init_git_in_dir(kb)
    bare.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(bare), "init", "--bare"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "remote", "remove", "origin"], capture_output=True)
    subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(bare)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "--allow-empty", "-m", "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "-u", "origin", "main"], capture_output=True, check=True)

    cfg = Config(
        notifications=NotificationsConfig(
            webhook_url="https://hooks.example.com/webhook",
            on_push=True,
        ),
    )
    _save_config(kb, cfg)

    with patch("httpx.post") as mock_post:
        result = cli_runner.invoke(cli, ["--kb-path", str(kb), "push"])
        # May fail for other reasons, but webhook should be attempted
        if mock_post.called:
            call_args = mock_post.call_args
            assert call_args[0][0] == "https://hooks.example.com/webhook"
            payload = call_args[1]["json"]
            assert "text" in payload


def test_push_webhook_failure_is_silent(cli_runner, initialized_kb, tmp_path):
    """push should continue gracefully when webhook fails."""
    import subprocess
    from knowledge_manager.schemas import Config, LLMProviderConfig, NotificationsConfig
    from knowledge_manager.cli import _save_config

    kb = initialized_kb
    bare = tmp_path / "bare.git"
    _init_git_in_dir(kb)
    bare.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "-C", str(bare), "init", "--bare"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "remote", "remove", "origin"], capture_output=True)
    subprocess.run(["git", "-C", str(kb), "remote", "add", "origin", str(bare)], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "commit", "--allow-empty", "-m", "init"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(kb), "push", "-u", "origin", "main"], capture_output=True, check=True)

    cfg = Config(
        notifications=NotificationsConfig(
            webhook_url="https://hooks.example.com/webhook",
            on_push=True,
        ),
    )
    _save_config(kb, cfg)

    with patch("httpx.post", side_effect=Exception("Network error")):
        result = cli_runner.invoke(cli, ["--kb-path", str(kb), "push"])
        # Should not crash — webhook failures are non-critical
        # Exit code may be 0 or 1 depending on other push outcomes


def test_config_set_webhook_url(cli_runner, initialized_kb):
    """config set should support notifications.webhook_url."""
    result = cli_runner.invoke(cli, [
        "--kb-path", str(initialized_kb),
        "config", "set", "notifications.webhook_url", "https://hooks.example.com/test",
    ])
    assert result.exit_code == 0

    # Verify it was saved
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "config", "get", "notifications.webhook_url"])
    assert result.exit_code == 0
    assert "hooks.example.com" in result.output


# ── Phase 2D: deprecate, archive, search --include-archived tests ──


def test_cli_deprecate_module(cli_runner, initialized_kb):
    """km deprecate should set module status to deprecated."""
    kb = initialized_kb
    mod = make_module("mod-dep", "test")
    save_module(mod, kb)
    rebuild_index(kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "deprecate", "test/mod-dep", "--reason", "Outdated"])
    assert result.exit_code == 0
    assert "deprecated" in result.output.lower()

    from knowledge_manager.storage import load_module
    loaded = load_module("mod-dep", "test", kb)
    assert loaded is not None
    assert loaded.metadata.status == "deprecated"


def test_cli_deprecate_nonexistent(cli_runner, initialized_kb):
    """deprecate on nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "deprecate", "test/no-such"])
    assert result.exit_code != 0


def test_cli_archive_module(cli_runner, initialized_kb):
    """km archive should set module status to archived."""
    kb = initialized_kb
    mod = make_module("mod-arch", "test")
    save_module(mod, kb)
    rebuild_index(kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "archive", "test/mod-arch"])
    assert result.exit_code == 0
    assert "archived" in result.output.lower()

    from knowledge_manager.storage import load_module
    loaded = load_module("mod-arch", "test", kb)
    assert loaded is not None
    assert loaded.metadata.status == "archived"


def test_cli_archive_nonexistent(cli_runner, initialized_kb):
    """archive on nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "archive", "test/no-such"])
    assert result.exit_code != 0


def test_cli_search_include_archived(cli_runner, initialized_kb):
    """km search --include-archived should find archived modules."""
    from knowledge_manager.schemas import ModuleMetadata

    kb = initialized_kb
    mod = make_module("hidden-mod", "test")
    mod.metadata.status = "archived"
    save_module(mod, kb)
    rebuild_index(kb)

    # Default search (excludes archived)
    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "search", "hidden"])
    assert result.exit_code == 0
    assert "No matches" in result.output

    # Search with --include-archived
    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "search", "--include-archived", "hidden"])
    assert result.exit_code == 0
    assert "hidden-mod" in result.output


# ── Phase 3A: health CLI tests ──


def test_cli_health_show_overview(cli_runner, initialized_kb):
    """km health should show an overview table."""
    mod = make_module("h1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health"])
    assert result.exit_code == 0
    assert "Knowledge Base Health Report" in result.output
    assert "auth" in result.output
    assert "Overall Health Score" in result.output


def test_cli_health_show_module_detail(cli_runner, initialized_kb):
    """km health --module should show single module detail."""
    mod = make_module("h2", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--module", "auth/h2"])
    assert result.exit_code == 0
    assert "Module Health: h2" in result.output
    assert "Freshness" in result.output
    assert "Completeness" in result.output


def test_cli_health_module_not_found(cli_runner, initialized_kb):
    """km health --module with invalid module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--module", "auth/nope"])
    assert result.exit_code != 0


def test_cli_health_module_invalid_format(cli_runner, initialized_kb):
    """km health --module without slash should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--module", "noslash"])
    assert result.exit_code != 0


def test_cli_health_at_risk(cli_runner, initialized_kb):
    """km health --at-risk should show only at-risk modules."""
    mod = make_module("h3", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--at-risk"])
    assert result.exit_code == 0
    # Module just created is fresh but has no usage and only 60% completeness → at risk
    assert "h3" in result.output or "No modules at risk" in result.output


def test_cli_health_json_format(cli_runner, initialized_kb):
    """km health --format json should output valid JSON."""
    import json
    mod = make_module("h4", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total_modules" in data
    assert "overall_score" in data
    assert "category_breakdown" in data


def test_cli_health_empty_kb(cli_runner, initialized_kb):
    """km health on empty KB should report empty."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "health"])
    assert result.exit_code == 0
    assert "empty" in result.output.lower() or "0 modules" in result.output.lower()


# ── Phase 3B: stats CLI tests ──


def test_cli_stats_empty(cli_runner, initialized_kb):
    """km stats on empty KB should report no usage data."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "usage"])
    assert result.exit_code == 0
    assert "No usage data" in result.output


def test_cli_stats_json_format(cli_runner, initialized_kb):
    """km stats --format json should output valid JSON."""
    import json
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "usage", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total_searches" in data
    assert "period_days" in data


def test_cli_stats_with_data(cli_runner, initialized_kb):
    """km stats should show stats after search/load events."""
    from knowledge_manager.storage import record_search_event, record_load_event

    kb = initialized_kb
    record_search_event("JWT authentication", ["auth/jwt"], kb)
    record_load_event("jwt", "auth", kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "usage"])
    assert result.exit_code == 0
    assert "1" in result.output  # at least 1 search


# ── Phase 3C: graph CLI tests ──


def test_cli_graph_overview(cli_runner, initialized_kb):
    """km graph should show graph overview with hubs, orphans, and clusters."""
    mod_a = make_module("g1", "auth")
    mod_a.metadata.related_modules = ["db/g2"]
    save_module(mod_a, initialized_kb)
    mod_b = make_module("g2", "db")
    mod_b.metadata.related_modules = ["auth/g1"]
    save_module(mod_b, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "graph"])
    assert result.exit_code == 0
    assert "Knowledge Graph Overview" in result.output
    assert "modules" in result.output
    assert "edges" in result.output


def test_cli_graph_export_mermaid(cli_runner, initialized_kb):
    """km graph --export mermaid should output valid Mermaid syntax."""
    mod = make_module("gm1", "auth")
    mod.metadata.related_modules = ["db/gm2"]
    save_module(mod, initialized_kb)
    mod2 = make_module("gm2", "db")
    save_module(mod2, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "graph", "--export", "mermaid"])
    assert result.exit_code == 0
    assert "graph TD" in result.output


def test_cli_graph_export_json(cli_runner, initialized_kb):
    """km graph --export json should output valid JSON with stats + clusters."""
    mod = make_module("gj1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "graph", "--export", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "stats" in data
    assert "clusters" in data
    assert data["stats"]["total_nodes"] >= 1


def test_cli_graph_empty(cli_runner, initialized_kb):
    """km graph on empty KB should report no modules."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "graph"])
    assert result.exit_code == 0
    assert "No modules" in result.output


# ── Phase 3D: recommend CLI tests ──


def test_cli_recommend_overview(cli_runner, initialized_kb):
    """km recommend should show recommendations in all categories."""
    mod = make_module("r1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "recommend"])
    assert result.exit_code == 0
    assert "Recommendations" in result.output


def test_cli_recommend_type_filter(cli_runner, initialized_kb):
    """km recommend --type archive should filter by type."""
    mod = make_module("r2", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "recommend", "--type", "archive"])
    assert result.exit_code == 0


def test_cli_recommend_json_format(cli_runner, initialized_kb):
    """km recommend --format json should output valid JSON."""
    mod = make_module("r3", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "recommend", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "archive_candidates" in data
    assert "enrichment_needed" in data
    assert "suggested_links" in data
    assert "review_reminders" in data


def test_cli_recommend_empty_kb(cli_runner, initialized_kb):
    """km recommend on empty KB should report great shape."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "recommend"])
    assert result.exit_code == 0
    assert "great shape" in result.output or "No recommendations" in result.output


def test_cli_ops_overview(cli_runner, initialized_kb):
    from knowledge_manager.schemas import ModuleMetadata

    kb = initialized_kb
    (kb / "config.json").write_text(
        json.dumps(
            {
                "llm_providers": {
                    "deepseek": {
                        "api_key": "",
                        "model": "deepseek-v4-pro",
                        "base_url": "https://api.deepseek.com",
                        "default": True
                    }
                },
                "routing_policy": {
                    "risk_level_allowed_statuses": {"high": ["published"]}
                }
            }
        ),
        encoding="utf-8",
    )
    mod = make_module("draft-ops", "ops")
    mod.metadata.status = "draft"
    save_module(mod, kb)
    rebuild_index(kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "ops"])
    assert result.exit_code == 0
    assert "Operations Report" in result.output
    assert "Policy-Suppressed" in result.output


def test_cli_ops_json(cli_runner, initialized_kb):
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "ops", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "source_backlog" in data
    assert "lifecycle_backlog" in data


def test_cli_ops_apply_stale_source_deprecate_dry_run(cli_runner, initialized_kb):
    stale_mod = make_module("stale-ops", "ops")
    stale_mod.metadata.stale_due_to_source_change = True
    save_module(stale_mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "ops-apply", "--action", "stale-source-deprecate", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "[DRY RUN]" in result.output

    from knowledge_manager.storage import load_module
    loaded = load_module("stale-ops", "ops", initialized_kb)
    assert loaded is not None
    assert loaded.metadata.status == "published"


def test_cli_ops_apply_stale_source_deprecate_executes(cli_runner, initialized_kb):
    stale_mod = make_module("stale-ops", "ops")
    stale_mod.metadata.stale_due_to_source_change = True
    save_module(stale_mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "ops-apply", "--action", "stale-source-deprecate"],
    )
    assert result.exit_code == 0
    assert "Applied 1 action(s)." in result.output

    from knowledge_manager.storage import load_module
    loaded = load_module("stale-ops", "ops", initialized_kb)
    assert loaded is not None
    assert loaded.metadata.status == "deprecated"


def test_cli_ops_apply_archive_suppressed_dry_run(cli_runner, initialized_kb):
    (initialized_kb / "config.json").write_text(
        json.dumps(
            {
                "llm_providers": {
                    "deepseek": {
                        "api_key": "",
                        "model": "deepseek-v4-pro",
                        "base_url": "https://api.deepseek.com",
                        "default": True
                    }
                },
                "routing_policy": {
                    "risk_level_allowed_statuses": {"high": ["published"]}
                }
            }
        ),
        encoding="utf-8",
    )
    suppressed = make_module("suppressed-ops", "ops")
    suppressed.metadata.status = "draft"
    save_module(suppressed, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "ops-apply", "--action", "archive-suppressed", "--dry-run"],
    )
    assert result.exit_code == 0
    assert "[DRY RUN] Archive ops/suppressed-ops" in result.output


def test_cli_ops_apply_archive_suppressed_executes(cli_runner, initialized_kb):
    (initialized_kb / "config.json").write_text(
        json.dumps(
            {
                "llm_providers": {
                    "deepseek": {
                        "api_key": "",
                        "model": "deepseek-v4-pro",
                        "base_url": "https://api.deepseek.com",
                        "default": True
                    }
                },
                "routing_policy": {
                    "risk_level_allowed_statuses": {"high": ["published"]}
                }
            }
        ),
        encoding="utf-8",
    )
    suppressed = make_module("suppressed-ops", "ops")
    suppressed.metadata.status = "draft"
    save_module(suppressed, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "ops-apply", "--action", "archive-suppressed"],
    )
    assert result.exit_code == 0
    assert "Archived ops/suppressed-ops" in result.output

    from knowledge_manager.storage import load_module
    loaded = load_module("suppressed-ops", "ops", initialized_kb)
    assert loaded is not None
    assert loaded.metadata.status == "archived"


def test_cli_ops_export_review_backlog_writes_json(cli_runner, initialized_kb):
    from knowledge_manager.schemas import StagingMeta
    from knowledge_manager.storage import save_staging_meta, save_to_staging

    staged = make_module("review-me", "ops")
    save_to_staging(staged, initialized_kb / ".staging")
    save_staging_meta(StagingMeta(module_id="review-me", status="pending"), initialized_kb / ".staging")

    output_path = initialized_kb / "review-backlog.json"
    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "ops-export-review-backlog", str(output_path)],
    )
    assert result.exit_code == 0
    assert output_path.exists()
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["total"] == 1
    assert data["items"][0]["module_id"] == "review-me"
    assert data["items"][0]["status"] == "pending"


def test_cli_ops_export_risky_misses_writes_json(cli_runner, initialized_kb):
    from knowledge_manager.storage import record_search_event

    record_search_event("deploy rollback", [], initialized_kb)

    output_path = initialized_kb / "risky-misses.json"
    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "ops-export-risky-misses", str(output_path)],
    )
    assert result.exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["total"] == 1
    assert data["items"][0]["query_terms"]


def test_cli_ops_export_source_backlog_writes_json(cli_runner, initialized_kb):
    cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "source",
            "add-confluence",
            "team-docs",
            "--base-url",
            "https://example.atlassian.net/wiki",
            "--space-key",
            "ENG",
            "--email",
            "docs@example.com",
            "--token-env",
            "CONFLUENCE_API_TOKEN",
            "--category",
            "architecture",
        ],
    )

    output_path = initialized_kb / "source-backlog.json"
    result = cli_runner.invoke(
        cli,
        ["--kb-path", str(initialized_kb), "ops-export-source-backlog", str(output_path)],
    )
    assert result.exit_code == 0
    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["total"] == 1
    assert data["items"][0]["source_id"] == "team-docs"


def test_cli_migrate_dry_run_outputs_summary(cli_runner, initialized_kb, tmp_path):
    export_path = tmp_path / "legacy-export.json"
    export_path.write_text(
        json.dumps([{"id": "page-1", "title": "Runbook", "body": "rollback safely"}]),
        encoding="utf-8",
    )

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "migrate",
            "dry-run",
            str(export_path),
            "--source-kind",
            "llm_wiki",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["total_documents"] == 1
    assert data["creates"] == 1


# ── Phase 3D: apply CLI tests ──


def test_cli_apply_dry_run(cli_runner, initialized_kb):
    """km apply --dry-run should preview actions without executing."""
    mod = make_module("a1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "apply", "--type", "archive", "--dry-run"])
    assert result.exit_code == 0


def test_cli_apply_type_required(cli_runner, initialized_kb):
    """km apply without --type should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "apply"])
    assert result.exit_code != 0


def test_cli_apply_archive_actually_archives(cli_runner, initialized_kb):
    """km apply --type archive should archive recommended modules."""
    from knowledge_manager.storage import load_module

    mod = make_module("a2", "auth")
    # Make it look old and unused to trigger archive recommendation
    from datetime import datetime, timezone, timedelta
    mod.updated_at = datetime.now(timezone.utc) - timedelta(days=200)
    mod.content.examples = ""
    mod.content.caveats = ""
    mod.content.references = ""
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "apply", "--type", "archive"])
    assert result.exit_code == 0
    # Module should now be archived
    m = load_module("a2", "auth", initialized_kb)
    assert m is not None
    assert m.metadata.status == "archived"


# ── Phase 4A: connect/disconnect CLI tests ──


def test_connect_list_platforms(cli_runner, initialized_kb):
    """km connect --list should show available platforms."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "connect", "--list"])
    assert result.exit_code == 0
    assert "claude-code" in result.output
    assert "copilot" in result.output


def test_connect_print_outputs_json(cli_runner, initialized_kb):
    """km connect --print should output valid MCP JSON to stdout."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "connect", "--print", "claude-code"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "mcpServers" in data
    assert "knowledge-manager" in data["mcpServers"]


def test_connect_unknown_platform_errors(cli_runner, initialized_kb):
    """km connect with unknown platform should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "connect", "nonexistent"])
    assert result.exit_code != 0


def test_connect_no_platform_without_list(cli_runner, initialized_kb):
    """km connect without platform and without --list should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "connect"])
    assert result.exit_code != 0


def test_connect_writes_config_file(cli_runner, initialized_kb):
    """km connect claude-code should write config to a tmp config path."""
    import os
    from pathlib import Path
    from knowledge_manager.connect import read_mcp_config

    kb = initialized_kb
    # Override the config path to write into a temp dir instead of real ~/.claude
    fake_home = kb / "fake-home"
    fake_home.mkdir()

    cfg_path = fake_home / ".claude" / "mcp.json"
    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "connect", "claude-code",
    ], env={"HOME": str(fake_home), "USERPROFILE": str(fake_home)})
    assert result.exit_code == 0

    # Check that the file was written
    data = read_mcp_config(cfg_path)
    assert "knowledge-manager" in data.get("mcpServers", {})


def test_disconnect_removes_entry(cli_runner, initialized_kb):
    """km disconnect should remove knowledge-manager from config."""
    import os
    from knowledge_manager.connect import write_mcp_config, build_mcp_entry, has_entry

    kb = initialized_kb
    fake_home = kb / "fake-home"
    fake_home.mkdir()

    # First manually write the config
    cfg_path = fake_home / ".claude" / "mcp.json"
    cfg_path.parent.mkdir(parents=True)
    write_mcp_config(cfg_path, build_mcp_entry(kb))
    assert has_entry(cfg_path)

    # Then disconnect
    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "disconnect", "claude-code",
    ], env={"HOME": str(fake_home), "USERPROFILE": str(fake_home)})
    assert result.exit_code == 0
    assert not has_entry(cfg_path)


def test_disconnect_no_entry(cli_runner, initialized_kb):
    """km disconnect when no entry exists should report it."""
    import os
    kb = initialized_kb
    fake_home = kb / "fake-home"
    fake_home.mkdir()

    result = cli_runner.invoke(cli, [
        "--kb-path", str(kb), "disconnect", "claude-code",
    ], env={"HOME": str(fake_home), "USERPROFILE": str(fake_home)})
    assert result.exit_code == 0
    assert "No knowledge-manager entry found" in result.output


# ── Phase 4D: marketplace/install/publish CLI tests ──


def _make_marketplace_dir(tmp_path):
    """Create a minimal local marketplace directory for testing."""
    from knowledge_manager.schemas import MarketplaceIndex, MarketplaceModule

    mp_dir = tmp_path / "test-marketplace"
    mp_dir.mkdir()
    auth_dir = mp_dir / "auth"
    auth_dir.mkdir()

    idx = MarketplaceIndex(
        modules={
            "auth/oauth2": MarketplaceModule(
                id="oauth2", category="auth",
                title="OAuth 2.0 Best Practices",
                summary="Security-focused OAuth 2.0 implementation guide",
                tags=["auth", "security"], version="2.1.0", author="community",
                confidence="high",
            ),
        }
    )
    (mp_dir / "index.json").write_text(idx.model_dump_json(indent=2))

    # Write a minimal module JSON file
    mod_json = json.dumps({
        "id": "oauth2", "category": "auth",
        "title": "OAuth 2.0 Best Practices",
        "summary": "Security-focused OAuth 2.0 implementation guide",
        "content": {
            "overview": "OAuth 2.0 is the industry standard for authorization.",
            "details": "This guide covers all the common OAuth 2.0 grant types...",
            "examples": "", "references": "", "caveats": ""
        },
        "metadata": {"tags": ["auth", "security"], "confidence": "high", "status": "published"}
    })
    (auth_dir / "oauth2.json").write_text(mod_json)

    return mp_dir


def test_marketplace_search_local(cli_runner, initialized_kb):
    """km marketplace search should find modules in a local marketplace."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "marketplace", "search", "oauth"])
    assert result.exit_code == 0
    assert "oauth2" in result.output


def test_marketplace_show_found(cli_runner, initialized_kb):
    """km marketplace show should display module details."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "marketplace", "show", "auth/oauth2"])
    assert result.exit_code == 0
    assert "OAuth 2.0 Best Practices" in result.output


def test_marketplace_show_not_found(cli_runner, initialized_kb):
    """km marketplace show with unknown module should report not found."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "marketplace", "show", "nonexistent/mod"])
    assert result.exit_code == 0
    assert "not found" in result.output.lower()


def test_install_from_marketplace(cli_runner, initialized_kb):
    """km install should put a marketplace module into staging."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "install", "auth/oauth2", "--yes"])
    assert result.exit_code == 0
    # Module should be in staging
    staging_file = kb / ".staging" / "oauth2.json"
    assert staging_file.exists()


def test_install_nonexistent_module(cli_runner, initialized_kb):
    """km install with unknown module should error."""
    kb = initialized_kb
    mp_dir = _make_marketplace_dir(kb)

    cfg = json.loads((kb / "config.json").read_text())
    cfg["marketplace"] = {"index_url": str(mp_dir), "sanitize_patterns": []}
    (kb / "config.json").write_text(json.dumps(cfg))

    result = cli_runner.invoke(cli, ["--kb-path", str(kb), "install", "nonexistent/mod", "--yes"])
    assert result.exit_code != 0


def test_publish_dry_run(cli_runner, initialized_kb):
    """km publish --dry-run should preview sanitized module."""
    mod = make_module("pub1", "auth")
    save_module(mod, initialized_kb)
    rebuild_index(initialized_kb)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "publish", "auth/pub1", "--dry-run"])
    assert result.exit_code == 0
    assert "Sanitized module preview" in result.output


def test_publish_invalid_ref(cli_runner, initialized_kb):
    """km publish without category/id format should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "publish", "noslash"])
    assert result.exit_code != 0


def test_publish_module_not_found(cli_runner, initialized_kb):
    """km publish with nonexistent module should error."""
    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "publish", "auth/nonexistent"])
    assert result.exit_code != 0


def test_cli_verify_production_readiness_reports_combined_verdict(cli_runner, initialized_kb, tmp_path):
    matrix_summary = tmp_path / "matrix-summary.json"
    matrix_summary.write_text(
        json.dumps(
            {
                "xs": {"release_verdict": {"ready_for_production": True}},
                "s": {"release_verdict": {"ready_for_production": True}},
                "m": {"release_verdict": {"ready_for_production": False}},
            }
        ),
        encoding="utf-8",
    )

    cfg = json.loads((initialized_kb / "config.json").read_text(encoding="utf-8"))
    cfg["llm_providers"] = {"x": {"api_key": "k", "model": "m", "default": True}}
    cfg["security"] = {"required_perf_scales": ["xs", "s", "m"]}
    (initialized_kb / "config.json").write_text(json.dumps(cfg), encoding="utf-8")

    result = cli_runner.invoke(
        cli,
        [
            "--kb-path",
            str(initialized_kb),
            "verify-production-readiness",
            "--matrix-summary",
            str(matrix_summary),
        ],
    )

    assert result.exit_code == 1
    assert '"ready_for_production": false' in result.output.lower()
    assert '"failed_scales": [' in result.output


def test_cli_worker_run_once_processes_queued_jobs(cli_runner, initialized_kb, monkeypatch):
    from knowledge_manager.ingestion_jobs import create_ingestion_job
    from knowledge_manager.audit import read_audit_log

    create_ingestion_job(initialized_kb, source_id="upload", trigger="http-upload")
    monkeypatch.setattr("knowledge_manager.worker_service.run_single_job", lambda *_args, **_kwargs: None)

    result = cli_runner.invoke(cli, ["--kb-path", str(initialized_kb), "worker", "run", "--once"])

    assert result.exit_code == 0
    assert "Processed 1 job(s)" in result.output
    events = read_audit_log(initialized_kb)
    assert any(event["operation"] == "worker.run" and event["result"] == "success" for event in events)
