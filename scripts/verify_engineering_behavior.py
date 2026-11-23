"""通过真实 CLI 与公开存储读取验证审核、图更新和恢复，保留独立证据。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


def main() -> int:
    """创建隔离知识库，驱动真实命令并检查磁盘结果，退出后保留证据。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    from knowledge_manager.schemas import Module, ModuleContent
    from knowledge_manager.storage import load_index, load_module, save_module, save_to_staging

    records: list[dict] = []
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")

    def run(command: list[str], expected: int = 0) -> subprocess.CompletedProcess[str]:
        """同时记录动作、输出和退出码，不将失败改判为成功。"""
        result = subprocess.run(command, capture_output=True, encoding="utf-8", env=environment)
        records.append(
            {
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        )
        if result.returncode != expected:
            raise RuntimeError(f"Command exited {result.returncode}: {command}")
        return result

    report: dict = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "commands": records,
        "ok": False,
        "provider_mode": "recovery drill uses deterministic provider fault injection",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="engineering-drive-") as scratch:
            kb = Path(scratch) / "kb"
            cli = [sys.executable, "-m", "knowledge_manager", "--kb-path", str(kb)]
            version = run([sys.executable, "-m", "knowledge_manager", "--version"])
            report["runtime"] = {"python": sys.version, "version": version.stdout.strip()}
            run([sys.executable, "-m", "knowledge_manager", "init", str(kb)])
            module = Module(
                id="verified-review",
                category="engineering",
                title="Verified review module",
                summary="A module used to verify real CLI review behavior",
                content=ModuleContent(
                    overview="Useful review overview",
                    details="Useful detailed engineering explanation",
                ),
            )
            save_to_staging(module, kb / ".staging")
            run(cli + ["review", "approve", module.id])
            first = load_module(module.id, module.category, kb)
            assert first is not None
            before = first.model_dump(mode="json")
            run(cli + ["review", "approve", module.id])
            after = load_module(module.id, module.category, kb)
            assert after is not None and after.model_dump(mode="json") == before
            search = run(cli + ["search", "verified"])
            assert module.id in search.stdout
            source = module.model_copy(deep=True, update={"id": "verified-source"})
            source.metadata.related_modules = [f"{module.category}/{module.id}"]
            save_module(source, kb)
            module.summary = "Updated summary preserves the real incoming module relationship"
            save_module(module, kb)
            index = load_index(kb)
            assert index is not None
            assert index.graph[f"{source.category}/{source.id}"] == [
                f"{module.category}/{module.id}"
            ]
            report["review_retry_preserves_module"] = True
            report["incoming_relation_preserved"] = True
            (output / "published-module.json").write_text(
                after.model_dump_json(indent=2), encoding="utf-8"
            )
            (output / "index.json").write_text(index.model_dump_json(indent=2), encoding="utf-8")
            root = Path(__file__).resolve().parents[1]
            run(
                [
                    sys.executable,
                    str(root / "scripts/run_ingestion_recovery_drill.py"),
                    "--kb-path",
                    str(Path(scratch) / "recovery"),
                    "--output",
                    str(output / "recovery.json"),
                ]
            )
            recovery = json.loads((output / "recovery.json").read_text(encoding="utf-8"))
            assert (
                recovery["ok"]
                and recovery["staged_module_valid"]
                and recovery["staging_metadata_present"]
            )
            report["ok"] = True
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        (output / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(
        json.dumps({"ok": report["ok"], "report": str(output / "report.json")}, ensure_ascii=False)
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
