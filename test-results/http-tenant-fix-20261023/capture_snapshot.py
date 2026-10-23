"""Record the exact source/config/test inputs used by this local verification."""
import hashlib
import json
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
files = [root / name for name in ("AGENTS.md", "pyproject.toml", "poetry.lock")]
for directory in ("src", "tests", "scripts"):
    files.extend((root / directory).rglob("*.py"))
payload = {
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
    "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=root, text=True).strip(),
    "environment": "audit-only-windows",
    "sha256": {
        str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(files)
    },
}
target = Path(__file__).with_name("snapshot.json")
target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"Recorded {len(payload['sha256'])} inputs at {target}")
