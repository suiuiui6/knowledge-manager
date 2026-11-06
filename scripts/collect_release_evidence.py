from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _run(command: str) -> dict[str, object]:
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
        "ok": result.returncode == 0,
    }


def _write_summary(release_dir: Path, steps: list[dict[str, object]]) -> tuple[dict[str, object], Path]:
    summary_path = release_dir / "release-evidence-collection.json"
    passed_step_names = [str(step["name"]) for step in steps if step["ok"]]
    failed_step_names = [str(step["name"]) for step in steps if not step["ok"]]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_dir": str(release_dir),
        "ok": all(bool(step["ok"]) for step in steps),
        "step_counts": {
            "total": len(steps),
            "passed": len(passed_step_names),
            "failed": len(failed_step_names),
        },
        "passed_step_names": passed_step_names,
        "failed_step_names": failed_step_names,
        "steps": steps,
        "artifacts": {
            "verify_install_smoke_path": str(release_dir / "verify-install-smoke.json"),
            "verify_production_readiness_path": str(release_dir / "verify-production-readiness.json"),
            "verify_deployment_path": str(release_dir / "verify-deployment.json"),
            "release_support_bundle_path": str(release_dir / "release-support-bundle.json"),
            "host_deploy_proof_path": str(release_dir / "host-deploy-proof.json"),
            "verify_release_artifacts_path": str(release_dir / "verify-release-artifacts.json"),
            "release_evidence_collection_path": str(summary_path),
        },
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload, summary_path


def _print_text_summary(payload: dict[str, object], steps: list[dict[str, object]], summary_path: Path) -> None:
    for step in steps:
        status = "PASS" if step["ok"] else "FAIL"
        print(f"[{status}] {step['name']}: {step['command']}")
    for name, path in payload["artifacts"].items():
        print(f"{name}={path}")
    print(f"summary={summary_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--km-command", default="km")
    parser.add_argument("--kb-path", type=Path)
    parser.add_argument("--base-url")
    parser.add_argument("--matrix-summary", type=Path)
    parser.add_argument("--skip-install-smoke", action="store_true")
    parser.add_argument("--install-smoke-command", default=None)
    parser.add_argument("--readiness-command", default=None)
    parser.add_argument("--deployment-command", default=None)
    parser.add_argument("--support-bundle-command", default=None)
    parser.add_argument("--host-proof-command", default=None)
    parser.add_argument("--release-verifier-command", default=None)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    release_dir = args.release_dir
    release_dir.mkdir(parents=True, exist_ok=True)
    project_root = args.project_root.resolve()

    install_smoke_command = args.install_smoke_command or (
        f'{args.python} "{project_root / "scripts" / "verify_install_smoke.py"}" '
        f'--project-root "{project_root}" --python {args.python} --format json > "{release_dir / "verify-install-smoke.json"}"'
    )
    readiness_command = args.readiness_command
    if readiness_command is None and args.kb_path is not None and args.matrix_summary is not None:
        readiness_command = (
            f'{args.km_command} --kb-path "{args.kb_path}" verify-production-readiness '
            f'--matrix-summary "{args.matrix_summary}" > "{release_dir / "verify-production-readiness.json"}"'
        )
    deployment_command = args.deployment_command
    if (
        deployment_command is None
        and args.kb_path is not None
        and args.base_url is not None
        and args.matrix_summary is not None
    ):
        deployment_command = (
            f'{args.km_command} --kb-path "{args.kb_path}" verify-deployment '
            f'--base-url "{args.base_url}" --matrix-summary "{args.matrix_summary}" --format json > "{release_dir / "verify-deployment.json"}"'
        )
    support_bundle_command = args.support_bundle_command
    if support_bundle_command is None and args.kb_path is not None and args.matrix_summary is not None:
        support_bundle_command = (
            f'{args.km_command} --kb-path "{args.kb_path}" support bundle '
            f'--output-dir "{release_dir}" --matrix-summary "{args.matrix_summary}"'
        )
    host_proof_command = args.host_proof_command or (
        f'{args.python} "{project_root / "scripts" / "collect_host_deploy_proof.py"}" '
        f'--output-dir "{release_dir}" --format json'
    )
    release_verifier_command = args.release_verifier_command or (
        f'{args.python} "{project_root / "scripts" / "verify_release_artifacts.py"}" '
        f'--release-dir "{release_dir}" --format json'
    )

    steps: list[dict[str, object]] = []
    install_smoke_artifact = release_dir / "verify-install-smoke.json"
    readiness_artifact = release_dir / "verify-production-readiness.json"
    deployment_artifact = release_dir / "verify-deployment.json"
    support_bundle_artifact = release_dir / "release-support-bundle.json"
    if args.skip_install_smoke and not install_smoke_artifact.exists():
        steps.append(
            {
                "name": "install_smoke_precondition",
                "command": "",
                "returncode": 1,
                "stdout": "",
                "stderr": (
                    "verify-install-smoke.json is missing; remove --skip-install-smoke "
                    "or provide an existing install smoke artifact in the release directory."
                ),
                "ok": False,
            }
        )
    elif not args.skip_install_smoke:
        steps.append({"name": "install_smoke", **_run(install_smoke_command)})
    if readiness_command is None and not readiness_artifact.exists():
        steps.append(
            {
                "name": "readiness_precondition",
                "command": "",
                "returncode": 1,
                "stdout": "",
                "stderr": (
                    "verify-production-readiness.json is missing; provide --readiness-command "
                    "or both --kb-path and --matrix-summary so it can be generated."
                ),
                "ok": False,
            }
        )
    elif readiness_command is not None:
        steps.append({"name": "readiness", **_run(readiness_command)})
    if deployment_command is None and not deployment_artifact.exists():
        steps.append(
            {
                "name": "deployment_precondition",
                "command": "",
                "returncode": 1,
                "stdout": "",
                "stderr": (
                    "verify-deployment.json is missing; provide --deployment-command "
                    "or all of --kb-path, --base-url, and --matrix-summary so it can be generated."
                ),
                "ok": False,
            }
        )
    elif deployment_command is not None:
        steps.append({"name": "deployment", **_run(deployment_command)})
    if support_bundle_command is None and not support_bundle_artifact.exists():
        steps.append(
            {
                "name": "support_bundle_precondition",
                "command": "",
                "returncode": 1,
                "stdout": "",
                "stderr": (
                    "release-support-bundle.json is missing; provide --support-bundle-command "
                    "or both --kb-path and --matrix-summary so it can be generated."
                ),
                "ok": False,
            }
        )
    if any(not step["ok"] for step in steps):
        payload, summary_path = _write_summary(release_dir, steps)
        if args.format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _print_text_summary(payload, steps, summary_path)
        return 1
    steps.append({"name": "host_proof", **_run(host_proof_command)})

    payload, summary_path = _write_summary(release_dir, steps)
    if support_bundle_command is not None:
        steps.append({"name": "support_bundle_refresh_pre_verify", **_run(support_bundle_command)})
    steps.append({"name": "release_verifier", **_run(release_verifier_command)})
    payload, summary_path = _write_summary(release_dir, steps)
    if support_bundle_command is not None:
        steps.append({"name": "support_bundle_refresh_final", **_run(support_bundle_command)})
    payload, summary_path = _write_summary(release_dir, steps)

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_text_summary(payload, steps, summary_path)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
