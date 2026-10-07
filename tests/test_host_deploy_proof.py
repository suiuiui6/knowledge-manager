import json
import subprocess
import sys
from pathlib import Path


def test_collect_host_deploy_proof_writes_expected_files(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output_dir = tmp_path / "release-artifacts"
    script = root / "scripts" / "collect_host_deploy_proof.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--output-dir",
            str(output_dir),
            "--api-unit-command",
            f"{sys.executable} -c \"print('[Service]\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui')\"",
            "--worker-unit-command",
            f"{sys.executable} -c \"print('[Service]\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0')\"",
            "--caddy-validate-command",
            f"{sys.executable} -c \"print('Valid configuration')\"",
            "--logrotate-check-command",
            f"{sys.executable} -c \"print('Handling 2 logs')\"",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        cwd=root,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert (output_dir / "knowledge-manager-api.unit.txt").exists()
    assert (output_dir / "knowledge-manager-worker.unit.txt").exists()
    assert (output_dir / "caddy-validate.txt").exists()
    assert (output_dir / "logrotate-check.txt").exists()
    assert (output_dir / "host-deploy-proof.json").exists()


def test_collect_host_deploy_proof_script_and_docs_reference_release_dir_capture():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "collect_host_deploy_proof.py").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    runbook = (root / "docs" / "runbooks" / "deploy-single-node.md").read_text(encoding="utf-8")

    assert "knowledge-manager-api.unit.txt" in script
    assert "knowledge-manager-worker.unit.txt" in script
    assert "caddy-validate.txt" in script
    assert "logrotate-check.txt" in script
    assert "systemctl cat knowledge-manager-api" in script
    assert "caddy validate --config /etc/caddy/Caddyfile" in script
    assert "logrotate -d /etc/logrotate.d/knowledge-manager" in script
    assert 'python3.11 /opt/knowledge-manager/scripts/collect_host_deploy_proof.py --output-dir "$RELEASE_DIR"' in readme
    assert 'python3.11 /opt/knowledge-manager/scripts/collect_host_deploy_proof.py --output-dir "$RELEASE_DIR"' in runbook


def test_collect_host_deploy_proof_rejects_http_only_caddy_config(tmp_path):
    root = Path(__file__).resolve().parents[1]
    output_dir = tmp_path / "release-artifacts"
    script = root / "scripts" / "collect_host_deploy_proof.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--output-dir",
            str(output_dir),
            "--api-unit-command",
            f"{sys.executable} -c \"print('[Service]\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui')\"",
            "--worker-unit-command",
            f"{sys.executable} -c \"print('[Service]\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0')\"",
            "--caddy-validate-command",
            (
                f"{sys.executable} -c \"print('Valid configuration\\n"
                "{\"level\":\"warn\",\"msg\":\"server is listening only on the HTTP port, so no automatic HTTPS will be applied to this server\"}')\""
            ),
            "--logrotate-check-command",
            f"{sys.executable} -c \"print('Handling 2 logs')\"",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        cwd=root,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["deploy_artifact_proof_complete"] is False
    assert "deploy-artifact-proof:caddy-validate.txt" in payload["invalid"]
