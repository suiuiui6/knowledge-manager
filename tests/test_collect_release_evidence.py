import json
import subprocess
import sys
from pathlib import Path


def test_collect_release_evidence_fails_clearly_when_readiness_and_deployment_inputs_are_missing(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--skip-install-smoke",
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
    assert [step["name"] for step in payload["steps"]] == [
        "install_smoke_precondition",
        "readiness_precondition",
        "deployment_precondition",
        "support_bundle_precondition",
    ]
    assert "verify-install-smoke.json is missing" in payload["steps"][0]["stderr"]
    assert "verify-production-readiness.json is missing" in payload["steps"][1]["stderr"]
    assert "verify-deployment.json is missing" in payload["steps"][2]["stderr"]


def test_collect_release_evidence_fails_clearly_when_install_smoke_is_skipped_without_artifact(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()
    (release_dir / "verify-production-readiness.json").write_text(
        json.dumps({"ready_for_production": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-deployment.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--skip-install-smoke",
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
    assert payload["steps"][0]["name"] == "install_smoke_precondition"
    assert "verify-install-smoke.json is missing" in payload["steps"][0]["stderr"]


def test_collect_release_evidence_fails_clearly_when_support_bundle_inputs_are_missing(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()
    (release_dir / "verify-install-smoke.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-production-readiness.json").write_text(
        json.dumps({"ready_for_production": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-deployment.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--skip-install-smoke",
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
    assert payload["steps"][0]["name"] == "support_bundle_precondition"
    assert "release-support-bundle.json is missing" in payload["steps"][0]["stderr"]


def test_collect_release_evidence_can_orchestrate_readiness_and_deployment_commands(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()
    (release_dir / "verify-install-smoke.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    matrix_summary = tmp_path / "matrix-summary.json"
    matrix_summary.write_text("{}", encoding="utf-8")

    support_bundle_writer = (
        "import json, pathlib; "
        f"release_dir = pathlib.Path(r'{release_dir}'); "
        "host = release_dir / 'host-deploy-proof.json'; "
        "verifier = release_dir / 'verify-release-artifacts.json'; "
        "collection = release_dir / 'release-evidence-collection.json'; "
        "payload = {"
        "'release_evidence': {"
        "'complete': host.exists() and verifier.exists() and collection.exists(),"
        "'missing': ["
        "name for name, exists in ["
        "('host-deploy-proof.json', host.exists()),"
        "('verify-release-artifacts.json', verifier.exists()),"
        "('release-evidence-collection.json', collection.exists())"
        "] if not exists"
        "],"
        "'invalid': [],"
        "'backup_restore_drill_within_30_days': True,"
        "'deploy_artifact_proof_complete': host.exists(),"
        "'host_deploy_proof_path': str(host) if host.exists() else '',"
        "'verify_release_artifacts_path': str(verifier) if verifier.exists() else '',"
        "'release_evidence_collection_path': str(collection) if collection.exists() else '',"
        "'backup_bundle_path': str(release_dir / 'knowledge-manager-backup-20260614T120000Z.zip'),"
        "'backup_bundle_attachments': ["
        "'attachments/verify-production-readiness.json',"
        "'attachments/verify-deployment.json',"
        "'attachments/verify-install-smoke.json'"
        "]"
        "}"
        "}; "
        "(release_dir / 'release-support-bundle.json').write_text("
        "json.dumps(payload, ensure_ascii=False), encoding='utf-8'"
        ");"
    )

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--kb-path",
            "/opt/knowledge-manager/kb",
            "--base-url",
            "http://127.0.0.1:8420",
            "--matrix-summary",
            str(matrix_summary),
            "--skip-install-smoke",
            "--readiness-command",
            f'{sys.executable} -c "import pathlib; pathlib.Path(r\'{release_dir / "verify-production-readiness.json"}\').write_text(\'{{\\\"ready_for_production\\\": true}}\', encoding=\'utf-8\')"',
            "--deployment-command",
            f'{sys.executable} -c "import pathlib; pathlib.Path(r\'{release_dir / "verify-deployment.json"}\').write_text(\'{{\\\"ok\\\": true}}\', encoding=\'utf-8\')"',
            "--support-bundle-command",
            f'{sys.executable} -c "{support_bundle_writer}"',
            "--host-proof-command",
            (
                f'{sys.executable} "{root / "scripts" / "collect_host_deploy_proof.py"}" '
                f'--output-dir "{release_dir}" '
                f'--api-unit-command "{sys.executable} -c \\"print(\'[Service]\\\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\\\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui\')\\"" '
                f'--worker-unit-command "{sys.executable} -c \\"print(\'[Service]\\\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\\\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0\')\\"" '
                f'--caddy-validate-command "{sys.executable} -c \\"print(\'Valid configuration\')\\"" '
                f'--logrotate-check-command "{sys.executable} -c \\"print(\'Handling 2 logs\')\\"" '
                '--format json'
            ),
            "--release-verifier-command",
            f'{sys.executable} "{root / "scripts" / "verify_release_artifacts.py"}" --release-dir "{release_dir}" --format json',
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
    assert (release_dir / "verify-production-readiness.json").exists()
    assert (release_dir / "verify-deployment.json").exists()
    assert payload["artifacts"]["verify_production_readiness_path"] == str(
        release_dir / "verify-production-readiness.json"
    )
    assert payload["artifacts"]["verify_deployment_path"] == str(
        release_dir / "verify-deployment.json"
    )
    assert [step["name"] for step in payload["steps"]] == [
        "readiness",
        "deployment",
        "host_proof",
        "support_bundle_refresh_pre_verify",
        "release_verifier",
        "support_bundle_refresh_final",
    ]


def test_collect_release_evidence_can_generate_and_refresh_support_bundle(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()

    (release_dir / "verify-production-readiness.json").write_text(
        json.dumps({"ready_for_production": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-deployment.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-install-smoke.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "restore-verify-deployment.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "knowledge-manager-backup-20260614T120000Z.zip").write_text(
        "placeholder",
        encoding="utf-8",
    )

    support_bundle_writer = (
        "import json, pathlib; "
        f"release_dir = pathlib.Path(r'{release_dir}'); "
        "host = release_dir / 'host-deploy-proof.json'; "
        "verifier = release_dir / 'verify-release-artifacts.json'; "
        "collection = release_dir / 'release-evidence-collection.json'; "
        "payload = {"
        "'release_evidence': {"
        "'complete': host.exists() and verifier.exists() and collection.exists(),"
        "'missing': ["
        "name for name, exists in ["
        "('host-deploy-proof.json', host.exists()),"
        "('verify-release-artifacts.json', verifier.exists()),"
        "('release-evidence-collection.json', collection.exists())"
        "] if not exists"
        "],"
        "'invalid': [],"
        "'backup_restore_drill_within_30_days': True,"
        "'deploy_artifact_proof_complete': host.exists(),"
        "'host_deploy_proof_path': str(host) if host.exists() else '',"
        "'verify_release_artifacts_path': str(verifier) if verifier.exists() else '',"
        "'release_evidence_collection_path': str(collection) if collection.exists() else '',"
        "'backup_bundle_path': str(release_dir / 'knowledge-manager-backup-20260614T120000Z.zip'),"
        "'backup_bundle_attachments': ["
        "'attachments/verify-production-readiness.json',"
        "'attachments/verify-deployment.json',"
        "'attachments/verify-install-smoke.json'"
        "]"
        "}"
        "}; "
        "(release_dir / 'release-support-bundle.json').write_text("
        "json.dumps(payload, ensure_ascii=False), encoding='utf-8'"
        ");"
    )

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--skip-install-smoke",
            "--support-bundle-command",
            f'{sys.executable} -c "{support_bundle_writer}"',
            "--host-proof-command",
            (
                f'{sys.executable} "{root / "scripts" / "collect_host_deploy_proof.py"}" '
                f'--output-dir "{release_dir}" '
                f'--api-unit-command "{sys.executable} -c \\"print(\'[Service]\\\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\\\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui\')\\"" '
                f'--worker-unit-command "{sys.executable} -c \\"print(\'[Service]\\\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\\\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0\')\\"" '
                f'--caddy-validate-command "{sys.executable} -c \\"print(\'Valid configuration\')\\"" '
                f'--logrotate-check-command "{sys.executable} -c \\"print(\'Handling 2 logs\')\\"" '
                '--format json'
            ),
            "--release-verifier-command",
            f'{sys.executable} "{root / "scripts" / "verify_release_artifacts.py"}" --release-dir "{release_dir}" --format json',
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
    support_bundle = json.loads((release_dir / "release-support-bundle.json").read_text(encoding="utf-8"))
    assert support_bundle["release_evidence"]["complete"] is True
    assert support_bundle["release_evidence"]["missing"] == []
    assert support_bundle["release_evidence"]["host_deploy_proof_path"].endswith("host-deploy-proof.json")
    assert support_bundle["release_evidence"]["verify_release_artifacts_path"].endswith(
        "verify-release-artifacts.json"
    )
    assert support_bundle["release_evidence"]["release_evidence_collection_path"].endswith(
        "release-evidence-collection.json"
    )


def test_collect_release_evidence_runs_pipeline_and_writes_summary(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()
    (release_dir / "verify-install-smoke.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-production-readiness.json").write_text(
        json.dumps({"ready_for_production": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-deployment.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )

    (release_dir / "release-support-bundle.json").write_text(
        json.dumps(
            {
                "release_evidence": {
                    "complete": True,
                    "missing": [],
                    "invalid": [],
                    "backup_restore_drill_within_30_days": True,
                    "deploy_artifact_proof_complete": True,
                    "host_deploy_proof_path": str(release_dir / "host-deploy-proof.json"),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--skip-install-smoke",
            "--host-proof-command",
            (
                f'{sys.executable} "{root / "scripts" / "collect_host_deploy_proof.py"}" '
                f'--output-dir "{release_dir}" '
                f'--api-unit-command "{sys.executable} -c \\"print(\'[Service]\\\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\\\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui\')\\"" '
                f'--worker-unit-command "{sys.executable} -c \\"print(\'[Service]\\\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\\\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0\')\\"" '
                f'--caddy-validate-command "{sys.executable} -c \\"print(\'Valid configuration\')\\"" '
                f'--logrotate-check-command "{sys.executable} -c \\"print(\'Handling 2 logs\')\\"" '
                '--format json'
            ),
            "--release-verifier-command",
            f'{sys.executable} "{root / "scripts" / "verify_release_artifacts.py"}" --release-dir "{release_dir}" --format json',
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
    assert payload["step_counts"] == {"total": 2, "passed": 2, "failed": 0}
    assert payload["passed_step_names"] == ["host_proof", "release_verifier"]
    assert payload["failed_step_names"] == []
    assert payload["artifacts"]["verify_production_readiness_path"] == str(
        release_dir / "verify-production-readiness.json"
    )
    assert payload["artifacts"]["verify_deployment_path"] == str(
        release_dir / "verify-deployment.json"
    )
    assert payload["artifacts"]["host_deploy_proof_path"] == str(release_dir / "host-deploy-proof.json")
    assert payload["artifacts"]["verify_release_artifacts_path"] == str(
        release_dir / "verify-release-artifacts.json"
    )
    assert payload["artifacts"]["release_evidence_collection_path"] == str(
        release_dir / "release-evidence-collection.json"
    )
    assert payload["artifacts"]["release_support_bundle_path"] == str(
        release_dir / "release-support-bundle.json"
    )
    assert (release_dir / "host-deploy-proof.json").exists()
    assert (release_dir / "verify-release-artifacts.json").exists()
    assert (release_dir / "release-evidence-collection.json").exists()


def test_collect_release_evidence_text_output_lists_artifact_paths(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()
    (release_dir / "verify-install-smoke.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-production-readiness.json").write_text(
        json.dumps({"ready_for_production": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "verify-deployment.json").write_text(
        json.dumps({"ok": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (release_dir / "release-support-bundle.json").write_text(
        json.dumps(
            {
                "release_evidence": {
                    "complete": True,
                    "missing": [],
                    "invalid": [],
                    "backup_restore_drill_within_30_days": True,
                    "deploy_artifact_proof_complete": True,
                    "host_deploy_proof_path": str(release_dir / "host-deploy-proof.json"),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--skip-install-smoke",
            "--host-proof-command",
            (
                f'{sys.executable} "{root / "scripts" / "collect_host_deploy_proof.py"}" '
                f'--output-dir "{release_dir}" '
                f'--api-unit-command "{sys.executable} -c \\"print(\'[Service]\\\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\\\nExecStart=/opt/knowledge-manager/.venv/bin/km serve --ui\')\\"" '
                f'--worker-unit-command "{sys.executable} -c \\"print(\'[Service]\\\\nEnvironmentFile=/opt/knowledge-manager/.env.production\\\\nExecStart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0\')\\"" '
                f'--caddy-validate-command "{sys.executable} -c \\"print(\'Valid configuration\')\\"" '
                f'--logrotate-check-command "{sys.executable} -c \\"print(\'Handling 2 logs\')\\"" '
                '--format json'
            ),
            "--release-verifier-command",
            f'{sys.executable} "{root / "scripts" / "verify_release_artifacts.py"}" --release-dir "{release_dir}" --format json',
            "--format",
            "text",
        ],
        capture_output=True,
        text=True,
        cwd=root,
    )

    assert result.returncode == 0, result.stderr
    assert f"verify_install_smoke_path={release_dir / 'verify-install-smoke.json'}" in result.stdout
    assert (
        f"verify_production_readiness_path={release_dir / 'verify-production-readiness.json'}"
        in result.stdout
    )
    assert f"verify_deployment_path={release_dir / 'verify-deployment.json'}" in result.stdout
    assert f"release_support_bundle_path={release_dir / 'release-support-bundle.json'}" in result.stdout
    assert f"host_deploy_proof_path={release_dir / 'host-deploy-proof.json'}" in result.stdout
    assert f"verify_release_artifacts_path={release_dir / 'verify-release-artifacts.json'}" in result.stdout
    assert f"release_evidence_collection_path={release_dir / 'release-evidence-collection.json'}" in result.stdout


def test_collect_release_evidence_failure_text_output_lists_artifact_paths(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--skip-install-smoke",
            "--format",
            "text",
        ],
        capture_output=True,
        text=True,
        cwd=root,
    )

    assert result.returncode == 1
    assert "[FAIL] install_smoke_precondition:" in result.stdout
    assert f"verify_install_smoke_path={release_dir / 'verify-install-smoke.json'}" in result.stdout
    assert (
        f"verify_production_readiness_path={release_dir / 'verify-production-readiness.json'}"
        in result.stdout
    )
    assert f"verify_deployment_path={release_dir / 'verify-deployment.json'}" in result.stdout
    assert f"release_support_bundle_path={release_dir / 'release-support-bundle.json'}" in result.stdout
    assert f"host_deploy_proof_path={release_dir / 'host-deploy-proof.json'}" in result.stdout
    assert f"verify_release_artifacts_path={release_dir / 'verify-release-artifacts.json'}" in result.stdout
    assert f"release_evidence_collection_path={release_dir / 'release-evidence-collection.json'}" in result.stdout


def test_collect_release_evidence_json_summary_lists_failed_step_names(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()

    script = root / "scripts" / "collect_release_evidence.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
            "--skip-install-smoke",
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
    assert payload["step_counts"] == {"total": 4, "passed": 0, "failed": 4}
    assert payload["passed_step_names"] == []
    assert payload["failed_step_names"] == [
        "install_smoke_precondition",
        "readiness_precondition",
        "deployment_precondition",
        "support_bundle_precondition",
    ]


def test_collect_release_evidence_is_documented():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "collect_release_evidence.py").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    runbook = (root / "docs" / "runbooks" / "deploy-single-node.md").read_text(encoding="utf-8")

    assert "collect_host_deploy_proof.py" in script
    assert "verify_release_artifacts.py" in script
    assert "release-evidence-collection.json" in script
    assert (
        'python3.11 /opt/knowledge-manager/scripts/collect_release_evidence.py --release-dir "$RELEASE_DIR" '
        '--kb-path /opt/knowledge-manager/kb --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json>'
    ) in readme
    assert (
        'python3.11 /opt/knowledge-manager/scripts/collect_release_evidence.py --release-dir "$RELEASE_DIR" '
        '--kb-path /opt/knowledge-manager/kb --base-url http://127.0.0.1:8420 --matrix-summary <fresh-matrix-summary.json>'
    ) in runbook
