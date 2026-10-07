from __future__ import annotations

from pathlib import Path


def build_deploy_artifact_proofs(output_dir: Path) -> dict[str, str]:
    return {
        "api_unit_capture_path": str(output_dir / "knowledge-manager-api.unit.txt"),
        "worker_unit_capture_path": str(output_dir / "knowledge-manager-worker.unit.txt"),
        "caddy_validate_path": str(output_dir / "caddy-validate.txt"),
        "logrotate_check_path": str(output_dir / "logrotate-check.txt"),
    }


def validate_deploy_artifact_proofs(output_dir: Path) -> tuple[dict[str, str], list[str], bool]:
    proof_paths = {
        "knowledge-manager-api.unit.txt": output_dir / "knowledge-manager-api.unit.txt",
        "knowledge-manager-worker.unit.txt": output_dir / "knowledge-manager-worker.unit.txt",
        "caddy-validate.txt": output_dir / "caddy-validate.txt",
        "logrotate-check.txt": output_dir / "logrotate-check.txt",
    }
    invalid: list[str] = []
    missing = 0

    for name, path in proof_paths.items():
        if not path.exists():
            missing += 1
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError:
            invalid.append(f"deploy-artifact-proof:{name}")
            continue

        normalized = text.lower()
        if name == "knowledge-manager-api.unit.txt":
            valid = (
                "environmentfile=/opt/knowledge-manager/.env.production" in normalized
                and "execstart=/opt/knowledge-manager/.venv/bin/km serve --ui" in normalized
            )
        elif name == "knowledge-manager-worker.unit.txt":
            valid = (
                "environmentfile=/opt/knowledge-manager/.env.production" in normalized
                and "execstart=/opt/knowledge-manager/.venv/bin/km worker run --poll-interval 1.0" in normalized
            )
        elif name == "caddy-validate.txt":
            valid = (
                "valid configuration" in normalized
                and "error" not in normalized
                and "automatic https will be applied" not in normalized
                and "listening only on the http port" not in normalized
                and "no automatic https" not in normalized
            )
        else:
            valid = bool(normalized.strip()) and "error" not in normalized and "handling" in normalized

        if not valid:
            invalid.append(f"deploy-artifact-proof:{name}")

    return build_deploy_artifact_proofs(output_dir), invalid, missing == 0 and not invalid
