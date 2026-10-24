from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from knowledge_manager.backup_restore import (
    create_backup_bundle,
    inspect_backup_bundle,
    restore_backup_bundle,
)
from knowledge_manager.performance_benchmarks import _sum_file_bytes
from knowledge_manager.runtime_checks import evaluate_readiness, run_integrity_check
from knowledge_manager.storage import (
    list_modules,
    rebuild_derived_indexes,
    rebuild_index,
    search_modules,
)


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
    manifest = inspect_backup_bundle(bundle)["manifest"]
    restored_files_match = all(
        hashlib.sha256((target / name[3:]).read_bytes()).hexdigest() == digest
        for name, digest in manifest["sha256"].items()
        if name.startswith("kb/")
    )
    rebuild_index(target)
    rebuild_derived_indexes(target)
    integrity = run_integrity_check(target)
    readiness = evaluate_readiness(target)
    source_modules = {
        f"{module.category}/{module.id}": module.model_dump(mode="json")
        for module in list_modules(args.kb_path)
    }
    restored_modules = {
        f"{module.category}/{module.id}": module.model_dump(mode="json")
        for module in list_modules(target)
    }
    search_checks = []
    for key, module in list(source_modules.items())[:20]:
        query = module["title"]
        expected = [
            f"{item.module.category}/{item.module.id}"
            for item in search_modules(query, args.kb_path, limit=20)
        ]
        actual = [
            f"{item.module.category}/{item.module.id}"
            for item in search_modules(query, target, limit=20)
        ]
        search_checks.append(
            {
                "query": query,
                "expected": expected,
                "actual": actual,
                "ok": bool(expected) and expected == actual and key in actual,
            }
        )
    search_ok = bool(search_checks) and all(item["ok"] for item in search_checks)
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
        )
    except OSError:
        commit, dirty = "", True
    report = {
        "ok": integrity["ok"]
        and readiness["ready"]
        and restored_files_match
        and source_modules == restored_modules
        and search_ok,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "verification_scope": "offline restore, checksums, indexes, readiness, integrity, search",
        "source_kb": str(args.kb_path.resolve()),
        "restored_kb": str(target),
        "bundle": str(bundle),
        "commit": commit,
        "working_tree_dirty": dirty,
        "source_bytes": _sum_file_bytes(args.kb_path),
        "restored_bytes": _sum_file_bytes(target),
        "integrity": integrity,
        "readiness": readiness,
        "source_module_count": len(source_modules),
        "restored_module_count": len(restored_modules),
        "canonical_files_match": source_modules == restored_modules,
        "restored_files_match": restored_files_match,
        "verified_file_count": len(manifest["sha256"]),
        "search_checks": search_checks,
        "search_overlap": sorted(
            {key for item in search_checks for key in set(item["expected"]) & set(item["actual"])}
        ),
    }
    artifact = output / "restore-verify-deployment.json"
    artifact.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
