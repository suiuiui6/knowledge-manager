from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from knowledge_manager.deploy_proof import validate_deploy_artifact_proofs


def _run_capture(command: str, output_path: Path) -> dict[str, object]:
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
    )
    text = result.stdout
    if result.stderr:
        text = f"{text}{result.stderr}"
    output_path.write_text(text, encoding="utf-8")
    return {
        "command": command,
        "path": str(output_path),
        "returncode": result.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--api-unit-command", default="systemctl cat knowledge-manager-api")
    parser.add_argument("--worker-unit-command", default="systemctl cat knowledge-manager-worker")
    parser.add_argument("--caddy-validate-command", default="caddy validate --config /etc/caddy/Caddyfile")
    parser.add_argument("--logrotate-check-command", default="logrotate -d /etc/logrotate.d/knowledge-manager")
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    checks = [
        _run_capture(args.api_unit_command, output_dir / "knowledge-manager-api.unit.txt"),
        _run_capture(args.worker_unit_command, output_dir / "knowledge-manager-worker.unit.txt"),
        _run_capture(args.caddy_validate_command, output_dir / "caddy-validate.txt"),
        _run_capture(args.logrotate_check_command, output_dir / "logrotate-check.txt"),
    ]
    proof_paths, invalid, complete = validate_deploy_artifact_proofs(output_dir)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": all(check["returncode"] == 0 for check in checks) and complete,
        "checks": checks,
        "deploy_artifact_proofs": proof_paths,
        "deploy_artifact_proof_complete": complete,
        "invalid": invalid,
    }
    summary_path = output_dir / "host-deploy-proof.json"
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for check in checks:
            status = "PASS" if check["returncode"] == 0 else "FAIL"
            print(f"[{status}] {check['command']} -> {check['path']}")
        print(f"deploy_artifact_proof_complete={complete}")
        print(f"summary={summary_path}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
