import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from knowledge_manager.cli import cli


def make_test_dir(name: str) -> Path:
    root = Path(__file__).resolve().parents[1] / "tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}-{uuid4().hex}"
    path.mkdir()
    return path


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_backup_bundle_includes_hidden_operational_dirs_and_manifest():
    kb = make_test_dir("backup-kb")
    write_text(kb / "index.json", json.dumps({"version": "1.0"}))
    write_text(kb / ".audit" / "audit.jsonl", '{"ok":true}\n')
    write_text(kb / ".jobs" / "state.json", "{}")
    write_text(kb / ".cache" / "state.json", "{}")
    write_text(kb / ".changelog" / "2026-06-13.json", "[]")

    from scripts.backup_kb import create_backup_bundle, inspect_backup_bundle

    bundle = create_backup_bundle(kb, make_test_dir("backup-output"))
    summary = inspect_backup_bundle(bundle)

    assert "kb/.audit/audit.jsonl" in summary["files"]
    assert "kb/.jobs/state.json" in summary["files"]
    assert "kb/.cache/state.json" in summary["files"]
    assert "kb/.changelog/2026-06-13.json" in summary["files"]
    assert summary["manifest"]["restore_policy"] == "empty-target-only"


def test_backup_bundle_includes_attached_release_evidence():
    kb = make_test_dir("backup-kb-attachments")
    write_text(kb / "index.json", json.dumps({"version": "1.0"}))
    attachment = make_test_dir("backup-attachment") / "verify-production-readiness.json"
    write_text(attachment, '{"ready_for_production": true}')

    from scripts.backup_kb import create_backup_bundle, inspect_backup_bundle

    bundle = create_backup_bundle(kb, make_test_dir("backup-output-attachments"), attachments=[attachment])
    summary = inspect_backup_bundle(bundle)

    assert "attachments/verify-production-readiness.json" in summary["files"]
    assert summary["manifest"]["contents"]["attachments"] == ["attachments/verify-production-readiness.json"]


def test_restore_bundle_refuses_nonempty_target():
    kb = make_test_dir("restore-source")
    write_text(kb / "index.json", json.dumps({"version": "1.0"}))

    from scripts.backup_kb import create_backup_bundle
    from scripts.restore_kb import restore_backup_bundle

    bundle = create_backup_bundle(kb, make_test_dir("restore-output"))
    target = make_test_dir("restore-target")
    write_text(target / "keep.txt", "busy")

    with pytest.raises(ValueError, match="empty"):
        restore_backup_bundle(bundle, target)


def test_cli_backup_create_emits_bundle_path():
    from click.testing import CliRunner

    kb = make_test_dir("cli-backup-kb")
    write_text(kb / "index.json", json.dumps({"version": "1.0"}))
    output_dir = make_test_dir("cli-backup-output")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "backup",
            "create",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip().endswith(".zip")


def test_cli_backup_create_attaches_release_evidence():
    from click.testing import CliRunner

    kb = make_test_dir("cli-backup-attach-kb")
    write_text(kb / "index.json", json.dumps({"version": "1.0"}))
    output_dir = make_test_dir("cli-backup-attach-output")
    attachment = output_dir / "verify-deployment.json"
    write_text(attachment, '{"ok": true}')

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "backup",
            "create",
            "--output-dir",
            str(output_dir),
            "--attach",
            str(attachment),
        ],
    )

    assert result.exit_code == 0

    from scripts.backup_kb import inspect_backup_bundle

    summary = inspect_backup_bundle(Path(result.output.strip()))
    assert "attachments/verify-deployment.json" in summary["files"]
    assert summary["manifest"]["contents"]["attachments"] == ["attachments/verify-deployment.json"]


def test_cli_backup_create_works_without_repo_root_on_syspath(monkeypatch):
    from click.testing import CliRunner

    kb = make_test_dir("cli-backup-installed-kb")
    write_text(kb / "index.json", json.dumps({"version": "1.0"}))
    output_dir = make_test_dir("cli-backup-installed-output")

    repo_root = Path(__file__).resolve().parents[1]
    trimmed_path = []
    for entry in sys.path:
        if not entry:
            trimmed_path.append(entry)
            continue
        try:
            if Path(entry).resolve() == repo_root:
                continue
        except OSError:
            pass
        trimmed_path.append(entry)

    monkeypatch.setattr(sys, "path", trimmed_path)
    sys.modules.pop("scripts", None)
    sys.modules.pop("scripts.backup_kb", None)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "--kb-path",
            str(kb),
            "backup",
            "create",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    assert result.output.strip().endswith(".zip")


def test_cli_backup_restore_works_without_repo_root_on_syspath(monkeypatch):
    from click.testing import CliRunner
    from scripts.backup_kb import create_backup_bundle

    kb = make_test_dir("cli-restore-installed-kb")
    write_text(kb / "index.json", json.dumps({"version": "1.0"}))
    bundle = create_backup_bundle(kb, make_test_dir("cli-restore-installed-output"))
    target = make_test_dir("cli-restore-installed-target")

    repo_root = Path(__file__).resolve().parents[1]
    trimmed_path = []
    for entry in sys.path:
        if not entry:
            trimmed_path.append(entry)
            continue
        try:
            if Path(entry).resolve() == repo_root:
                continue
        except OSError:
            pass
        trimmed_path.append(entry)

    monkeypatch.setattr(sys, "path", trimmed_path)
    sys.modules.pop("scripts", None)
    sys.modules.pop("scripts.restore_kb", None)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "backup",
            "restore",
            "--bundle",
            str(bundle),
            "--target-kb",
            str(target),
        ],
    )

    assert result.exit_code == 0
    assert (target / "index.json").exists()
