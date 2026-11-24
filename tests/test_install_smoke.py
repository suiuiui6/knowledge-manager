"""安装冒烟必须明确跨进程文本协议并保留失败退出码。"""

import importlib.util
import os
from pathlib import Path
import sys


_spec = importlib.util.spec_from_file_location(
    "verify_install_smoke", Path(__file__).resolve().parents[1] / "scripts/verify_install_smoke.py"
)
assert _spec is not None and _spec.loader is not None
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


def test_run_uses_utf8_for_both_python_child_and_parent() -> None:
    env = {**os.environ, "PYTHONIOENCODING": "ascii"}
    result = smoke._run(
        [sys.executable, "-c", "import sys; print('中文输出'); sys.stderr.write('错误输出')"],
        env=env,
    )
    assert result["ok"] is True
    assert result["stdout"] == "中文输出\n"
    assert result["stderr"] == "错误输出"
    assert env["PYTHONIOENCODING"] == "ascii"


def test_run_preserves_failure_with_non_ascii_diagnostics() -> None:
    result = smoke._run([sys.executable, "-c", "import sys; sys.stderr.write('失败'); sys.exit(7)"])
    assert result["returncode"] == 7
    assert result["ok"] is False
    assert result["stderr"] == "失败"
