import json
import subprocess
import sys
from pathlib import Path


def test_verify_release_artifacts_accepts_complete_release_dir(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()

    host_proof = release_dir / "host-deploy-proof.json"
    host_proof.write_text(
        json.dumps(
            {
                "ok": True,
                "deploy_artifact_proof_complete": True,
                "invalid": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    support_bundle = release_dir / "release-support-bundle.json"
    support_bundle.write_text(
        json.dumps(
            {
                "release_evidence": {
                    "complete": True,
                    "missing": [],
                    "invalid": [],
                    "backup_restore_drill_within_30_days": True,
                    "deploy_artifact_proof_complete": True,
                    "host_deploy_proof_path": str(host_proof),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script = root / "scripts" / "verify_release_artifacts.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
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
    assert payload["release_support_bundle_path"] == str(support_bundle)
    assert payload["host_deploy_proof_path"] == str(host_proof)
    verifier_output = release_dir / "verify-release-artifacts.json"
    assert verifier_output.exists()
    persisted = json.loads(verifier_output.read_text(encoding="utf-8"))
    assert persisted["ok"] is True


def test_verify_release_artifacts_accepts_bundle_waiting_only_on_self_and_patches_bundle(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()

    host_proof = release_dir / "host-deploy-proof.json"
    host_proof.write_text(
        json.dumps(
            {
                "ok": True,
                "deploy_artifact_proof_complete": True,
                "invalid": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    support_bundle = release_dir / "release-support-bundle.json"
    support_bundle.write_text(
        json.dumps(
            {
                "release_evidence": {
                    "complete": False,
                    "missing": ["verify-release-artifacts.json"],
                    "invalid": [],
                    "backup_restore_drill_within_30_days": True,
                    "deploy_artifact_proof_complete": True,
                    "host_deploy_proof_path": str(host_proof),
                    "verify_release_artifacts_path": "",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script = root / "scripts" / "verify_release_artifacts.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
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
    updated_bundle = json.loads(support_bundle.read_text(encoding="utf-8"))
    assert updated_bundle["release_evidence"]["complete"] is True
    assert updated_bundle["release_evidence"]["missing"] == []
    assert updated_bundle["release_evidence"]["verify_release_artifacts_path"].endswith(
        "verify-release-artifacts.json"
    )


def test_verify_release_artifacts_accepts_pipeline_bundle_waiting_on_verifier_and_collection_refresh(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()

    host_proof = release_dir / "host-deploy-proof.json"
    host_proof.write_text(
        json.dumps(
            {
                "ok": True,
                "deploy_artifact_proof_complete": True,
                "invalid": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    collection = release_dir / "release-evidence-collection.json"
    collection.write_text(
        json.dumps(
            {
                "ok": False,
                "failed_step_names": ["release_verifier"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    stale_verifier = release_dir / "verify-release-artifacts.json"
    stale_verifier.write_text(
        json.dumps(
            {
                "ok": False,
                "invalid": ["release-support-bundle.json"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    support_bundle = release_dir / "release-support-bundle.json"
    support_bundle.write_text(
        json.dumps(
            {
                "release_evidence": {
                    "complete": False,
                    "missing": [],
                    "invalid": [
                        "verify-release-artifacts.json",
                        "release-evidence-collection.json",
                    ],
                    "backup_restore_drill_within_30_days": True,
                    "deploy_artifact_proof_complete": True,
                    "host_deploy_proof_path": str(host_proof),
                    "verify_release_artifacts_path": str(stale_verifier),
                    "release_evidence_collection_path": str(collection),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script = root / "scripts" / "verify_release_artifacts.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
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
    updated_bundle = json.loads(support_bundle.read_text(encoding="utf-8"))
    assert updated_bundle["release_evidence"]["complete"] is True
    assert updated_bundle["release_evidence"]["missing"] == []
    assert updated_bundle["release_evidence"]["invalid"] == []
    assert updated_bundle["release_evidence"]["release_evidence_collection_path"].endswith(
        "release-evidence-collection.json"
    )


def test_verify_release_artifacts_rejects_invalid_host_deploy_proof(tmp_path):
    root = Path(__file__).resolve().parents[1]
    release_dir = tmp_path / "release-artifacts"
    release_dir.mkdir()

    host_proof = release_dir / "host-deploy-proof.json"
    host_proof.write_text(
        json.dumps(
            {
                "ok": False,
                "deploy_artifact_proof_complete": False,
                "invalid": ["deploy-artifact-proof:caddy-validate.txt"],
            },
            ensure_ascii=False,
        ),
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
                    "host_deploy_proof_path": str(host_proof),
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    script = root / "scripts" / "verify_release_artifacts.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--release-dir",
            str(release_dir),
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
    assert "host-deploy-proof.json" in payload["invalid"]


def test_release_artifact_verifier_is_documented():
    root = Path(__file__).resolve().parents[1]
    script = (root / "scripts" / "verify_release_artifacts.py").read_text(encoding="utf-8")
    readme = (root / "README.md").read_text(encoding="utf-8")
    runbook = (root / "docs" / "runbooks" / "deploy-single-node.md").read_text(encoding="utf-8")
    checklist = (root / "docs" / "runbooks" / "production-release-checklist.md").read_text(
        encoding="utf-8"
    )

    assert "release-support-bundle.json" in script
    assert "host-deploy-proof.json" in script
    assert "verify-release-artifacts.json" in script
    assert 'python3.11 /opt/knowledge-manager/scripts/verify_release_artifacts.py --release-dir "$RELEASE_DIR"' in readme
    assert 'python3.11 /opt/knowledge-manager/scripts/verify_release_artifacts.py --release-dir "$RELEASE_DIR"' in runbook
    assert "verify-release-artifacts.json" in readme
    assert "verify-release-artifacts.json" in runbook
    assert "verify_release_artifacts.py" in checklist
