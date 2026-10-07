import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        capture_output=True,
        text=True,
    )
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "ok": result.returncode == 0,
    }


def _find_single_wheel(wheel_dir: Path) -> Path:
    wheels = sorted(wheel_dir.glob("knowledge_manager-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one wheel in {wheel_dir}, found {len(wheels)}")
    return wheels[0]


def _venv_bin_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def _trim_output(result: dict[str, object]) -> dict[str, object]:
    trimmed = dict(result)
    trimmed["stdout"] = str(trimmed["stdout"]).strip()
    trimmed["stderr"] = str(trimmed["stderr"]).strip()
    return trimmed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--python", dest="python_executable", default=sys.executable)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "text"], default="json")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    work_dir = args.work_dir.resolve() if args.work_dir is not None else None

    tmp_ctx = tempfile.TemporaryDirectory(prefix="km-install-smoke-", dir=str(work_dir) if work_dir else None)
    report: dict[str, object] = {
        "project_root": str(project_root),
        "python": args.python_executable,
        "checks": [],
    }

    def record(name: str, result: dict[str, object]) -> dict[str, object]:
        entry = {"name": name, **_trim_output(result)}
        report["checks"].append(entry)
        return entry

    try:
        tmp_root = Path(tmp_ctx.name)
        wheel_dir = tmp_root / "wheel"
        wheel_dir.mkdir(parents=True, exist_ok=True)
        venv_dir = tmp_root / "venv"
        kb_dir = tmp_root / "kb"

        build_result = record(
            "build_wheel",
            _run(
                [
                    args.python_executable,
                    "-m",
                    "pip",
                    "wheel",
                    str(project_root),
                    "--no-deps",
                    "-w",
                    str(wheel_dir),
                ],
                cwd=project_root,
            ),
        )
        if not build_result["ok"]:
            raise SystemExit(1)

        wheel_path = _find_single_wheel(wheel_dir)
        report["wheel_path"] = str(wheel_path)

        create_venv_result = record(
            "create_venv",
            _run([args.python_executable, "-m", "venv", str(venv_dir)]),
        )
        if not create_venv_result["ok"]:
            raise SystemExit(1)

        bin_dir = _venv_bin_dir(venv_dir)
        pip_path = bin_dir / "pip"
        km_path = bin_dir / "km"

        install_result = record(
            "install_wheel",
            _run(
                [
                    str(pip_path),
                    "install",
                    "--no-cache-dir",
                    "--force-reinstall",
                    str(wheel_path),
                ]
            ),
        )
        if not install_result["ok"]:
            raise SystemExit(1)

        version_result = record("km_version", _run([str(km_path), "--version"]))
        if not version_result["ok"]:
            raise SystemExit(1)

        init_result = record("km_init", _run([str(km_path), "init", str(kb_dir)]))
        if not init_result["ok"]:
            raise SystemExit(1)

        stats_result = record("km_stats", _run([str(km_path), "--kb-path", str(kb_dir), "stats"]))
        if not stats_result["ok"]:
            raise SystemExit(1)

        invalid_port_env = os.environ.copy()
        invalid_port_env["KM_KB_PATH"] = str(kb_dir)
        invalid_port_env["KM_UI_PORT"] = "not-a-port"
        invalid_port_result = record(
            "invalid_ui_port",
            _run([str(km_path), "stats"], env=invalid_port_env),
        )
        invalid_port_text = f"{invalid_port_result['stdout']}\n{invalid_port_result['stderr']}"
        invalid_port_result["ok"] = (
            invalid_port_result["returncode"] != 0 and "KM_UI_PORT" in invalid_port_text
        )
        if not invalid_port_result["ok"]:
            raise SystemExit(1)

        invalid_log_env = os.environ.copy()
        invalid_log_env["KM_KB_PATH"] = str(kb_dir)
        invalid_log_env["KM_LOG_LEVEL"] = "LOUD"
        invalid_log_result = record(
            "invalid_log_level",
            _run([str(km_path), "stats"], env=invalid_log_env),
        )
        invalid_log_text = f"{invalid_log_result['stdout']}\n{invalid_log_result['stderr']}"
        invalid_log_result["ok"] = (
            invalid_log_result["returncode"] != 0 and "KM_LOG_LEVEL" in invalid_log_text
        )
        if not invalid_log_result["ok"]:
            raise SystemExit(1)

        report["ok"] = all(bool(entry["ok"]) for entry in report["checks"])
    finally:
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            for entry in report.get("checks", []):
                status = "PASS" if entry["ok"] else "FAIL"
                print(f"[{status}] {entry['name']}: {' '.join(entry['command'])}")
            if "wheel_path" in report:
                print(f"wheel: {report['wheel_path']}")
        tmp_ctx.cleanup()

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
