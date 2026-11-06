from __future__ import annotations

import json
import hashlib
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from knowledge_manager.file_locks import serialized_write


APP_VERSION = "0.5.2"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


@serialized_write
def create_backup_bundle(kb_path: Path, output_dir: Path, attachments: list[Path] | None = None) -> Path:
    if not kb_path.exists():
        raise FileNotFoundError(f"Knowledge base not found: {kb_path}")

    ts = _timestamp()
    kb_resolved = kb_path.resolve()
    output_resolved = output_dir.resolve()
    if output_resolved == kb_resolved or kb_resolved in output_resolved.parents:
        raise ValueError("Backup output directory must be outside the source KB")
    output_dir.mkdir(parents=True, exist_ok=True)

    attached_files: list[str] = []
    for attachment in attachments or []:
        attached_files.append(f"attachments/{attachment.name}")

    file_hashes: dict[str, str] = {}
    for path in sorted(kb_path.rglob("*")):
        if path.is_file() and ".locks" not in path.relative_to(kb_path).parts and path.suffix != ".tmp":
            file_hashes[f"kb/{path.relative_to(kb_path).as_posix()}"] = hashlib.sha256(path.read_bytes()).hexdigest()
    for attachment in attachments or []:
        file_hashes[f"attachments/{attachment.name}"] = hashlib.sha256(attachment.read_bytes()).hexdigest()

    manifest = {
        "created_at": ts,
        "app_version": APP_VERSION,
        "source_kb_path": str(kb_path),
        "contents": {
            "kb_tree": "full recursive copy, including hidden operational directories under the KB root",
            "attachments": attached_files,
        },
        "restore_policy": "empty-target-only",
        "restore_includes": [
            "all visible KB content",
            "must-restore operational state such as .audit/, .jobs/, config, and release evidence attachments",
            "safe-to-rebuild derived state such as .cache/ when present",
            "manifest metadata required to validate restore semantics",
        ],
        "restore_tiers": {
            "must_restore": [
                "module content and index state",
                "config.json and auth or RBAC material stored under the KB root",
                ".audit/",
                ".jobs/",
                ".staging/",
                ".telemetry/",
                ".changelog/",
            ],
            "rebuildable_after_restore": [
                ".cache/",
                "derived search or recommendation artifacts that can be regenerated from the restored KB state",
            ],
        },
        "non_restored_items": [
            "systemd units are infra artifacts and are not copied into the restored KB",
            "reverse proxy config is infra-managed and is not copied into the restored KB",
        ],
        "sha256": file_hashes,
    }
    bundle_path = output_dir / f"knowledge-manager-backup-{ts}.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(kb_path.rglob("*")):
            if path.is_file() and ".locks" not in path.relative_to(kb_path).parts and path.suffix != ".tmp":
                zf.write(path, arcname=f"kb/{path.relative_to(kb_path).as_posix()}")
        for attachment in attachments or []:
            zf.write(attachment, arcname=f"attachments/{attachment.name}")
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return bundle_path


def inspect_backup_bundle(bundle_path: Path) -> dict:
    with zipfile.ZipFile(bundle_path) as zf:
        names = sorted(zf.namelist())
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    return {"files": names, "manifest": manifest}


def restore_backup_bundle(bundle_path: Path, target_kb: Path) -> Path:
    if target_kb.exists() and any(target_kb.iterdir()):
        raise ValueError("Restore target must be empty")

    target_kb.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(bundle_path) as zf:
        names = set(zf.namelist())
        if "manifest.json" not in names:
            raise ValueError("Backup bundle is missing manifest.json")
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        if manifest.get("restore_policy") != "empty-target-only":
            raise ValueError("Backup bundle restore policy is not supported")
        kb_entries = sorted(name for name in names if name.startswith("kb/") and not name.endswith("/"))
        if not kb_entries:
            raise ValueError("Backup bundle is missing kb/ content")
        hashes = manifest.get("sha256", {})
        for name in kb_entries:
            rel = Path(name).relative_to("kb")
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(f"Unsafe restore path: {name}")
            if name in hashes:
                digest = hashlib.sha256(zf.read(name)).hexdigest()
                if digest != hashes[name]:
                    raise ValueError(f"Backup checksum mismatch: {name}")
        for name in kb_entries:
            rel = Path(name).relative_to("kb")
            if rel.is_absolute() or ".." in rel.parts:
                raise ValueError(f"Unsafe restore path: {name}")
            dest = target_kb / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(name) as src, dest.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    return target_kb
