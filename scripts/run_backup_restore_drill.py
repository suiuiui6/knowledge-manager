from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from knowledge_manager.backup_restore import create_backup_bundle, restore_backup_bundle
from knowledge_manager.performance_benchmarks import _sum_file_bytes
from knowledge_manager.runtime_checks import evaluate_readiness, run_integrity_check
from knowledge_manager.storage import rebuild_derived_indexes, rebuild_index, search_modules


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / "restored-kb"
    bundle = create_backup_bundle(args.kb_path, output)
    restore_backup_bundle(bundle, target)
    rebuild_index(target)
    rebuild_derived_indexes(target)
    integrity = run_integrity_check(target)
    readiness = evaluate_readiness(target)
    expected_keys = {f"{item.module.category}/{item.module.id}" for item in search_modules("rollback", args.kb_path, limit=20)}
    restored_keys = {f"{item.module.category}/{item.module.id}" for item in search_modules("rollback", target, limit=20)}
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        commit = ""
    report = {
        "ok": integrity["ok"] and readiness["ready"] and bool(expected_keys & restored_keys),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_kb": str(args.kb_path.resolve()),
        "restored_kb": str(target),
        "bundle": str(bundle),
        "commit": commit,
        "source_bytes": _sum_file_bytes(args.kb_path),
        "restored_bytes": _sum_file_bytes(target),
        "integrity": integrity,
        "readiness": readiness,
        "search_overlap": sorted(expected_keys & restored_keys),
    }
    artifact = output / "restore-verify-deployment.json"
    artifact.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
