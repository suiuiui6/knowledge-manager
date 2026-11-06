from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    release_dir = args.release_dir
    support_bundle_path = release_dir / "release-support-bundle.json"
    invalid: list[str] = []
    missing: list[str] = []

    support_bundle = _load_json(support_bundle_path)
    if support_bundle is None:
        missing.append("release-support-bundle.json")
        release_evidence: dict = {}
    else:
        release_evidence = dict(support_bundle.get("release_evidence", {}))
        existing_missing = list(release_evidence.get("missing") or [])
        existing_invalid = list(release_evidence.get("invalid") or [])
        transitional_missing = sorted(
            item for item in existing_missing
            if item in {"verify-release-artifacts.json"}
        )
        transitional_invalid = sorted(
            item for item in existing_invalid
            if item in {"verify-release-artifacts.json", "release-evidence-collection.json"}
        )
        waiting_only_on_verifier = (
            not bool(release_evidence.get("complete"))
            and sorted(existing_missing) == transitional_missing
            and sorted(existing_invalid) == transitional_invalid
            and bool(transitional_missing or transitional_invalid)
        )
        if not bool(release_evidence.get("complete")) and not waiting_only_on_verifier:
            invalid.append("release-support-bundle.json")
        non_verifier_missing = [item for item in existing_missing if item != "verify-release-artifacts.json"]
        if non_verifier_missing:
            invalid.append("release-support-bundle.json")
        if existing_invalid and not waiting_only_on_verifier:
            invalid.append("release-support-bundle.json")
        if not bool(release_evidence.get("backup_restore_drill_within_30_days")):
            invalid.append("release-support-bundle.json")
        if not bool(release_evidence.get("deploy_artifact_proof_complete")):
            invalid.append("release-support-bundle.json")

    host_deploy_proof_path = Path(release_evidence.get("host_deploy_proof_path", "")) if release_evidence.get("host_deploy_proof_path") else None
    if host_deploy_proof_path is None:
        missing.append("host-deploy-proof.json")
        host_deploy_proof = None
    else:
        host_deploy_proof = _load_json(host_deploy_proof_path)
        if host_deploy_proof is None:
            invalid.append("host-deploy-proof.json")
        elif (
            not bool(host_deploy_proof.get("ok"))
            or not bool(host_deploy_proof.get("deploy_artifact_proof_complete"))
            or bool(host_deploy_proof.get("invalid"))
        ):
            invalid.append("host-deploy-proof.json")

    payload = {
        "ok": not missing and not invalid,
        "release_dir": str(release_dir),
        "release_support_bundle_path": str(support_bundle_path),
        "host_deploy_proof_path": str(host_deploy_proof_path) if host_deploy_proof_path is not None else "",
        "missing": missing,
        "invalid": sorted(set(invalid)),
    }
    verifier_output_path = release_dir / "verify-release-artifacts.json"
    verifier_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if isinstance(support_bundle, dict):
        release_evidence = dict(support_bundle.get("release_evidence", {}))
        release_evidence["verify_release_artifacts_path"] = str(verifier_output_path)
        if payload["ok"]:
            filtered_missing = [
                item for item in list(release_evidence.get("missing") or [])
                if item != "verify-release-artifacts.json"
            ]
            filtered_invalid = [
                item for item in list(release_evidence.get("invalid") or [])
                if item not in {"verify-release-artifacts.json", "release-evidence-collection.json"}
            ]
            release_evidence["missing"] = filtered_missing
            release_evidence["invalid"] = filtered_invalid
            release_evidence["complete"] = not filtered_missing and not filtered_invalid
        support_bundle["release_evidence"] = release_evidence
        support_bundle_path.write_text(json.dumps(support_bundle, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"ok={payload['ok']}")
        print(f"release_support_bundle_path={payload['release_support_bundle_path']}")
        print(f"host_deploy_proof_path={payload['host_deploy_proof_path']}")
        print(f"verify_release_artifacts_path={verifier_output_path}")
        if missing:
            print(f"missing={','.join(missing)}")
        if invalid:
            print(f"invalid={','.join(sorted(set(invalid)))}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
